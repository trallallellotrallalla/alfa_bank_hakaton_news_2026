import type { ChatAnswer, Citation, Company, Insight, Role } from '../types/insight';
import { ROLE_LABEL } from '../types/insight';

/**
 * Мок AI-аналитика: простая маршрутизация по намерениям поверх insight.v1.
 * Реальный бэкенд отвечает тем же форматом ChatAnswer через POST /chat.
 */

const fmt = (n: number, digits = 1) => n.toLocaleString('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const KEY_RATE = 14;

function profileCitation(company: Company): Citation {
    const parts = company.credit_line ? 'кредитная линия, платежи' : 'платежи, ВЭД';
    return { n: 1, label: `Профиль: ${parts}` };
}

function sourceCitations(insight: Insight, kinds: ('bank' | 'fact')[], start: number): Citation[] {
    const ids = new Set<string>();
    if (kinds.includes('bank')) insight.bank_view.forEach((b) => b.src.forEach((s) => ids.add(s)));
    if (kinds.includes('fact')) insight.facts.forEach((f) => f.src.forEach((s) => ids.add(s)));
    return [...ids].map((id, i) => {
        const src = insight.sources.find((s) => s.id === id)!;
        const prefix = src.kind === 'bank_research' ? 'ЦМИ' : src.publisher;
        return { n: start + i, label: `${prefix}: «${src.title}»`, source_id: id };
    });
}

function rateScenarios(company: Company): ChatAnswer | null {
    const cl = company.credit_line;
    if (!cl) return null;
    const q = (rate: number) => (cl.drawn_mln * (rate + cl.margin_pp)) / 100 / 4;
    const base = q(KEY_RATE);
    const soft = q(KEY_RATE - 1);
    const hard = q(KEY_RATE + 1);
    return {
        origins: ['ai', 'bank'],
        paragraphs: [
            `При текущей выборке кредитной линии (≈${cl.drawn_mln} млн ₽ из ${cl.limit_mln} млн ₽) процентные расходы в IV квартале составят около ${fmt(base)} млн ₽ — на ${fmt(base - soft)} млн ₽ больше, чем при снижении ставки до ${KEY_RATE - 1}% в октябре [1][2].`,
            'Банк ожидает сохранения ставки до декабря: данные по рынку труда не подтверждают охлаждения экономики [2][3].',
        ],
        table: {
            columns: ['Сценарий', 'КС в IV кв.', 'Проценты, млн ₽'],
            rows: [
                ['Базовый (банк) [2]', `${KEY_RATE}% до декабря`, fmt(base)],
                ['Мягкий', `${KEY_RATE - 1}% с октября`, fmt(soft)],
                ['Жёсткий', `${KEY_RATE + 1}% с октября`, fmt(hard)],
            ],
        },
        citations: [],
        slices: ['По месяцам', `По группе ${company.group_id}`, 'Как в прошлом году'],
    };
}

function decemberCut(company: Company): ChatAnswer | null {
    const cl = company.credit_line;
    if (!cl) return null;
    const month = (rate: number) => (cl.drawn_mln * (rate + cl.margin_pp)) / 100 / 12;
    const saving = month(KEY_RATE) - month(KEY_RATE - 1);
    return {
        origins: ['ai', 'bank'],
        paragraphs: [
            `Если ЦБ снизит ставку до ${KEY_RATE - 1}% на заседании в декабре, эффект для IV квартала почти нулевой: новая ставка начнёт действовать во второй половине декабря — экономия около ${fmt(saving / 2, 2)} млн ₽ [1].`,
            `Основной эффект придётся на I квартал 2027 года: около ${fmt(saving * 3)} млн ₽ экономии за квартал при текущей выборке. Это совпадает с базовым сценарием банка — возобновление снижения не раньше декабря [2].`,
        ],
        citations: [],
        slices: ['По месяцам', 'Сравнить с фиксацией ставки'],
    };
}

function groupAnswer(company: Company, insight: Insight): ChatAnswer {
    return {
        origins: ['ai'],
        paragraphs: [
            `В группу ${company.group_id} входит ${company.group_size} юрлица. Агент видит только данные юрлиц, к которым у вашей роли есть доступ в Альфа-Бизнесе [1].`,
            `Событие «${insight.title}» затрагивает в первую очередь ${company.short}: ${insight.why_you}. Для остальных юрлиц группы значимых признаков (кредиты с плавающей ставкой, ВЭД по этой теме) не найдено.`,
        ],
        citations: [],
        slices: ['По юрлицам', 'Только кредитные продукты'],
    };
}

function bankForecast(insight: Insight): ChatAnswer {
    if (!insight.bank_view.length) {
        return {
            origins: ['ai'],
            paragraphs: [
                'По этой теме у Альфа-Банка нет опубликованной аналитики — поэтому я не показываю «позицию банка». Ниже только факты из первоисточников.',
                ...insight.facts.map((f) => f.text),
            ],
            citations: [],
        };
    }
    return {
        origins: ['bank'],
        paragraphs: insight.bank_view.map((b) => `${b.text} [2]`),
        citations: [],
        slices: ['Сравнить с консенсусом', 'Как менялся прогноз'],
    };
}

function primarySources(insight: Insight): ChatAnswer {
    return {
        origins: ['ai'],
        paragraphs: [
            ...insight.facts.map((f) => `Факт: ${f.text}`),
            `Первоисточники: ${insight.sources.map((s) => `${s.publisher} — «${s.title}»`).join('; ')}.`,
        ],
        citations: [],
    };
}

function summaryAnswer(insight: Insight, role: Role): ChatAnswer {
    const why = insight.ai_inference.find((i) => i.kind === 'why_relevant');
    const cons = insight.ai_inference.filter((i) => i.kind !== 'why_relevant');
    const actions = [...insight.actions].sort((a, b) => Number(!!b.roles?.includes(role)) - Number(!!a.roles?.includes(role)));
    return {
        origins: insight.bank_view.length ? ['ai', 'bank'] : ['ai'],
        paragraphs: [
            why ? `${why.text} [1]` : insight.summary,
            ...cons.map((c) => c.text),
            `Для роли «${ROLE_LABEL[role]}» в первую очередь: ${actions[0]?.text.toLowerCase() ?? '—'}`,
        ],
        citations: [],
        slices: ['Подробнее о рисках', 'Подробнее о возможностях'],
    };
}

function clarify(insight: Insight): ChatAnswer {
    return {
        origins: ['ai'],
        paragraphs: ['Уточните, пожалуйста, что именно посчитать — так ответ будет точнее.'],
        citations: [],
        clarify: {
            question: 'Что вас интересует по этому событию?',
            options: insight.suggested_questions.slice(0, 3),
        },
    };
}

function withCitations(answer: ChatAnswer, company: Company, insight: Insight): ChatAnswer {
    if (answer.clarify) return answer;
    const cites: Citation[] = [profileCitation(company)];
    const kinds: ('bank' | 'fact')[] = answer.origins.includes('bank') ? ['bank'] : ['fact'];
    cites.push(...sourceCitations(insight, kinds, 2));
    return { ...answer, citations: cites, run_id: insight.run_id };
}

export function mockChatAnswer(question: string, company: Company, role: Role, insight: Insight, fxInsight?: Insight): ChatAnswer {
    const q = question.toLowerCase().trim();
    const words = q.split(/\s+/).filter(Boolean);

    let answer: ChatAnswer | null = null;
    if (/снизит|снизят|снижени[ея].*декабр|а если/.test(q)) answer = decemberCut(company);
    else if (/переплат|процент|расход.*кредит|сколько.*квартал/.test(q) && insight.topics.includes('rates')) answer = rateScenarios(company);
    else if (/групп|g-\d/.test(q)) answer = groupAnswer(company, insight);
    else if (/прогноз|мнени|позици|банк ждёт|банк ждет/.test(q)) answer = bankForecast(/курс|валют/.test(q) && fxInsight ? fxInsight : insight);
    else if (/первоисточ|источник|пишут/.test(q)) answer = primarySources(insight);
    else if (/курс|валют|юан|доллар|рубл/.test(q) && fxInsight) answer = summaryAnswer(fxInsight, role);
    else if (words.length <= 2) answer = clarify(insight);

    answer ??= summaryAnswer(insight, role);
    return withCitations(answer, company, /курс|валют|юан|доллар|рубл/.test(q) && fxInsight ? fxInsight : insight);
}

/** Шаги, которые агент «проговаривает», пока готовит ответ */
export const THINKING_STEPS = [
    'Агент читает профиль компании',
    'Агент ищет первоисточники',
    'Агент ищет позицию Альфа-Банка',
    'Агент считает влияние на компанию',
    'Агент проверяет ответ по источникам',
];
