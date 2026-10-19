import { useEffect, useRef, useState, type ReactNode } from 'react';

/** Выпадающий список для топбара: закрывается по клику вне и по Esc */
export function Dropdown({
    trigger,
    children,
    label,
}: {
    trigger: ReactNode;
    children: (close: () => void) => ReactNode;
    label: string;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!open) return;
        const onDown = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node)) setOpen(false);
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('mousedown', onDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);
    return (
        <div className="dropdown" ref={ref}>
            <button
                type="button"
                className="dropdown__trigger"
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-label={label}
                onClick={() => setOpen((o) => !o)}
            >
                {trigger}
            </button>
            {open && (
                <div className="dropdown__menu" role="listbox">
                    {children(() => setOpen(false))}
                </div>
            )}
        </div>
    );
}
