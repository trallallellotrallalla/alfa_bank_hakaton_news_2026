import type { ReactNode } from 'react';
import { Status } from '@alfalab/core-components-status';
import type { Impact, Origin } from '../types/insight';
import { IMPACT_LABEL } from '../types/insight';

type TagColor = 'red' | 'green' | 'orange' | 'blue' | 'grey';

/** Status из core-components в виде мягкой метки, как в макетах */
export function Tag({ color, children }: { color: TagColor; children: ReactNode }) {
    return (
        <Status view="muted-alt" color={color} size={20} uppercase={false} className="tag">
            {children}
        </Status>
    );
}

const IMPACT_COLOR: Record<Impact, TagColor> = { risk: 'red', opportunity: 'green', attention: 'orange', scenario: 'blue' };

export function ImpactTag({ impact }: { impact: Impact }) {
    return <Tag color={IMPACT_COLOR[impact]}>{IMPACT_LABEL[impact]}</Tag>;
}

const ORIGIN: Record<Origin | 'trace', { color: TagColor; label: string }> = {
    fact: { color: 'grey', label: 'Факт' },
    bank: { color: 'blue', label: 'Позиция банка' },
    ai: { color: 'orange', label: 'Вывод AI' },
    trace: { color: 'grey', label: 'Трасса' },
};

export function OriginTag({ origin, label }: { origin: Origin | 'trace'; label?: string }) {
    return <Tag color={ORIGIN[origin].color}>{label ?? ORIGIN[origin].label}</Tag>;
}
