import { useEffect, useState } from 'react';
import { Button } from '@alfalab/core-components-button';
import { Checkbox } from '@alfalab/core-components-checkbox';
import { Switch } from '@alfalab/core-components-switch';
import { ALL_TOPICS, useApp } from '../context/AppContext';
import { TOPIC_LABEL, type Topic } from '../types/insight';

/** «Уточнить профиль»: пользователь сам сужает темы и требует опору на позицию банка */
export function ProfileModal({ onClose }: { onClose: () => void }) {
    const { company, prefs, setPrefs } = useApp();
    const [topics, setTopics] = useState<Topic[]>(prefs.topics);
    const [onlyBankView, setOnlyBankView] = useState(prefs.onlyBankView);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    const toggle = (t: Topic) => setTopics((ts) => (ts.includes(t) ? ts.filter((x) => x !== t) : [...ts, t]));

    return (
        <div className="modal-backdrop" onMouseDown={onClose}>
            <div className="modal" role="dialog" aria-modal="true" aria-labelledby="profile-title" onMouseDown={(e) => e.stopPropagation()}>
                <h2 className="panel__title" id="profile-title">
                    Уточнить профиль
                </h2>
                <p className="text-secondary-13">
                    Агент учитывает это при отборе событий для {company?.name}. Признаки из банковских данных (ОКВЭД, продукты, ВЭД) меняются
                    только по данным банка.
                </p>
                <div className="modal__group">
                    <span className="text-tertiary-12">Темы, которые важны</span>
                    {ALL_TOPICS.map((t) => (
                        <Checkbox key={t} size={24} label={TOPIC_LABEL[t]} checked={topics.includes(t)} onChange={() => toggle(t)} />
                    ))}
                </div>
                <Switch
                    label="Только события с позицией Альфа-Банка"
                    hint="Скрыть события, где есть только вывод AI"
                    checked={onlyBankView}
                    onChange={(_, { checked }) => setOnlyBankView(checked)}
                />
                <div className="modal__actions">
                    <Button
                        view="primary"
                        size={48}
                        disabled={!topics.length}
                        onClick={() => {
                            setPrefs({ topics, onlyBankView });
                            onClose();
                        }}
                    >
                        Сохранить
                    </Button>
                    <Button view="secondary" size={48} onClick={onClose}>
                        Отмена
                    </Button>
                </div>
            </div>
        </div>
    );
}
