import { describe, expect, it } from 'vitest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from '../../../docs/insight.v1.schema.json';
import example from '../../../docs/insight.v1.example.json';
import type { Insight } from '../../types/insight';
import type { Interpretation } from '../../types/interpretation';
import { interpretationToInsight, toFeed, toInsight, toTrace } from './interpretation';
import { mockApi } from '../mock';

/** Все тестовые варианты ВЫХОДА: имя файла → содержимое */
const VARIANTS = Object.fromEntries(
    Object.entries(
        import.meta.glob<Interpretation>('../../../docs/vyhod-examples/*.json', { eager: true, import: 'default' }),
    ).map(([path, data]) => [path.split('/').pop()!.replace('.json', ''), data]),
);
const variant = (name: string) => structuredClone(VARIANTS[name]);

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

/** Ссылки целостны: каждый src указывает на источник, каждый признак вывода — на признак из features */
function expectConsistent(i: Insight) {
    const sourceIds = new Set(i.sources.map((s) => s.id));
    for (const ref of [...i.facts, ...i.bank_view].flatMap((x) => x.src)) expect(sourceIds).toContain(ref);
    const featureCodes = new Set(i.features.map((f) => f.code));
    for (const code of i.ai_inference.flatMap((x) => x.features)) expect(featureCodes).toContain(code);
}

describe('тестовые варианты ВЫХОДА', () => {
    it('найдены все 5 вариантов', () => {
        expect(Object.keys(VARIANTS).sort()).toEqual([
            '01-key-rate',
            '02-no-bank-view',
            '03-opportunity-only',
            '04-recommended-format',
            '05-minimal',
        ]);
    });

    for (const name of Object.keys(VARIANTS)) {
        it(`${name}: результат адаптера валиден по insight.v1 и ссылки целостны`, () => {
            const insight = interpretationToInsight(variant(name));
            const ok = validate(JSON.parse(JSON.stringify(insight)));
            expect(validate.errors ?? [], JSON.stringify(validate.errors, null, 2)).toEqual([]);
            expect(ok).toBe(true);
            expectConsistent(insight);
            expect(insight.company_id).toBe('U_176');
            expect(insight.trace.length).toBeGreaterThan(0);
            expect(insight.why_you).not.toBe('');
        });
    }
});

describe('проверка по схеме ловит ошибки', () => {
    it('инсайт без фактов и с неизвестным impact не проходит', () => {
        const broken = JSON.parse(JSON.stringify(interpretationToInsight(variant('01-key-rate'))));
        broken.facts = [];
        broken.impact = 'catastrophe';
        expect(validate(broken)).toBe(false);
        expect(validate.errors!.map((e) => e.instancePath)).toEqual(expect.arrayContaining(['/facts', '/impact']));
    });
});

describe('01-key-rate — исходный ВЫХОД', () => {
    const i = interpretationToInsight(variant('01-key-rate'));

    it('переносит идентификаторы и событие', () => {
        expect(i.event_id).toBe('1001');
        expect(i.run_id).toBe('INT_001');
        expect(i.title).toBe('ЦБ сохранил ключевую ставку на 14%');
        expect(i.published_at).toBe('2026-09-11T00:00:00+03:00');
    });

    it('раскладывает текст по происхождению: факт / позиция банка / вывод AI', () => {
        expect(i.facts).toHaveLength(1);
        expect(i.facts[0].src).toEqual(['news:1001']);
        expect(i.bank_view).toEqual([
            { text: 'Период быстрого удешевления кредитов приостановлен', src: ['analytics:cb_key_rate_14::p2::c1'] },
        ]);
        expect(i.ai_inference.filter((x) => x.kind === 'why_relevant')).toHaveLength(2); // why_it_matters + model_inference
        expect(i.ai_inference.filter((x) => x.kind === 'consequence_risk')).toHaveLength(2);
        expect(i.ai_inference.filter((x) => x.kind === 'consequence_opportunity')).toHaveLength(1);
        expect(i.actions.map((a) => a.id)).toEqual(['a1', 'a2']);
    });

    it('восстанавливает недостающее: impact, темы, уверенность, подписи сигналов', () => {
        expect(i.impact).toBe('risk');
        expect(i.topics).toContain('rates');
        expect(i.relevance).toBe(0.82);
        expect(i.confidence).toBe('high');
        expect(i.features).toEqual([expect.objectContaining({ code: 'credit_dependency', label: 'Зависимость от заёмного финансирования' })]);
        const chunk = i.sources.find((s) => s.kind === 'bank_research')!;
        expect(chunk.title).toBe('Ключевая ставка ЦБ РФ: ставка без изменения на 14,0%, риторика стала жестче, с. 2');
        expect(chunk.url).toBeUndefined();
    });

    it('восстанавливает трассу с пометкой', () => {
        expect(i.trace).toHaveLength(5);
        expect(i.trace[2].tool).toBe('analytics[cb_key_rate_14::p2::c1]');
        expect(i.trace[0].detail).toContain('восстановлено');
    });
});

describe('02-no-bank-view — аналитики банка нет', () => {
    const i = interpretationToInsight(variant('02-no-bank-view'));

    it('позиция банка пустая, источников аналитики нет', () => {
        expect(i.bank_view).toEqual([]);
        expect(i.sources.some((s) => s.kind === 'bank_research')).toBe(false);
        expect(i.trace[2].detail).toContain('не найдена');
    });

    it('только риски → impact risk, тема «контрагенты»', () => {
        expect(i.impact).toBe('risk');
        expect(i.topics).toContain('counterparty');
        expect(i.features.map((f) => f.code)).toEqual(['counterparty_risk']);
    });
});

describe('03-opportunity-only — только возможности', () => {
    const i = interpretationToInsight(variant('03-opportunity-only'));

    it('impact opportunity, рисков нет, тема «сырьё»', () => {
        expect(i.impact).toBe('opportunity');
        expect(i.ai_inference.some((x) => x.kind === 'consequence_risk')).toBe(false);
        expect(i.topics).toContain('commodities');
        expect(i.confidence).toBe('medium');
    });
});

describe('04-recommended-format — рекомендованный формат', () => {
    const i = interpretationToInsight(variant('04-recommended-format'));

    it('берёт поля бэкенда вместо восстановленных', () => {
        expect(i.relevance).toBe(0.91);
        expect(i.impact).toBe('risk');
        expect(i.topics).toEqual(['regulation']);
        expect(i.summary).toBe('Тариф за проезд грузовиков массой свыше 12 т по федеральным трассам вырастет на 8%.');
        expect(i.published_at).toBe('2026-10-08T15:20:00+03:00');
        expect(i.confidence).toBe('high');
        expect(i.suggested_questions[0]).toBe('Сколько мы доплатим за «Платон» в 2027 году?');
    });

    it('факты и позиция банка — массивы со ссылками на свои источники', () => {
        expect(i.facts.map((f) => f.src)).toEqual([['news:1004'], ['news:1004b']]);
        expect(i.bank_view).toHaveLength(2);
        expect(i.bank_view[1].src).toEqual(['analytics:transport_review::p3::c4']);
        expect(i.sources.every((s) => s.url)).toBe(true);
    });

    it('сигналы, веса и роли не теряются', () => {
        expect(i.features.map((f) => [f.code, f.weight])).toEqual([
            ['fleet_heavy_trucks', 0.94],
            ['federal_routes_share', 0.71],
            ['fixed_price_contracts', 0.52],
        ]);
        expect(i.ai_inference.find((x) => x.kind === 'consequence_opportunity')!.features).toEqual(['fixed_price_contracts']);
        expect(i.actions[1].roles).toEqual(['ceo', 'procurement']);
        expect(i.why_you).toBe('парк грузовиков свыше 12 т · доля рейсов по федеральным трассам');
    });

    it('трасса бэкенда сохраняется вместе с повторным поиском', () => {
        expect(i.trace).toHaveLength(6);
        expect(i.trace[0].title).toBe('1. Профиль клиента');
        expect(i.trace[3].state).toBe('retry');
        expect(i.basis).toContain('Противоречие устранено');
    });
});

describe('05-minimal — только обязательные поля', () => {
    const i = interpretationToInsight(variant('05-minimal'));

    it('пустые списки вместо падения', () => {
        expect(i.actions).toEqual([]);
        expect(i.bank_view).toEqual([]);
        expect(i.features).toEqual([]);
        expect(i.ai_inference).toEqual([expect.objectContaining({ kind: 'why_relevant', features: [] })]);
    });

    it('impact attention, уверенность medium, подсказки по умолчанию', () => {
        expect(i.impact).toBe('attention');
        expect(i.confidence).toBe('medium');
        expect(i.suggested_questions.length).toBeGreaterThan(0);
        expect(i.why_you).toBe('Для компании это пока долгосрочный сигнал: прямого влияния на текущие рейсы нет.');
    });
});

describe('нормализация ответов API', () => {
    const all = Object.keys(VARIANTS).map(variant);

    it('/feed: массив ВЫХОДов сортируется по релевантности', () => {
        const feed = toFeed(all, 'U_176', 'cfo');
        expect(feed.items.map((x) => x.event_id)).toEqual(['1004', '1001', '1002', '1003', '1005']);
        expect(feed.company_id).toBe('U_176');
    });

    it('/feed: принимает и { items: [...] }', () => {
        expect(toFeed({ items: all.slice(0, 2) }, 'U_176', 'cfo').items).toHaveLength(2);
    });

    it('/events: insight.v1 проходит без изменений, мусор — ошибка', () => {
        expect(toInsight(example)).toBe(example);
        expect(() => toInsight({ foo: 1 })).toThrow('ни на insight.v1, ни на ВЫХОД');
    });

    it('/trace: строится из ВЫХОДА', () => {
        const t = toTrace(variant('04-recommended-format'));
        expect(t.run_id).toBe('INT_004');
        expect(t.retries).toBe(1);
        expect(t.duration_s).toBe(9.1);
    });

    it('мок-лента U_176 показывает все варианты', async () => {
        const feed = await mockApi.getFeed('U_176', 'cfo');
        expect(feed.items).toHaveLength(5);
    });
});
