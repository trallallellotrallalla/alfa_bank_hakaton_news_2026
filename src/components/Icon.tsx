import bell from '../assets/icons/bell.svg';
import search from '../assets/icons/search.svg';
import chevronDown from '../assets/icons/chevron-down.svg';
import chevronRightInverted from '../assets/icons/chevron-right-inverted.svg';
import home from '../assets/icons/home.svg';
import navAccounts from '../assets/icons/nav-accounts.svg';
import navPayments from '../assets/icons/nav-payments.svg';
import navCredits from '../assets/icons/nav-credits.svg';
import navDocs from '../assets/icons/nav-docs.svg';
import navNews from '../assets/icons/nav-news.svg';
import navReports from '../assets/icons/nav-reports.svg';
import navSettings from '../assets/icons/nav-settings.svg';
import sparkle from '../assets/icons/sparkle.svg';
import link from '../assets/icons/link.svg';
import shield from '../assets/icons/shield.svg';
import stepDone from '../assets/icons/step-done.svg';
import stepRetry from '../assets/icons/step-retry.svg';

const ICONS = {
    bell,
    search,
    chevronDown,
    chevronRightInverted,
    home,
    navAccounts,
    navPayments,
    navCredits,
    navDocs,
    navNews,
    navReports,
    navSettings,
    sparkle,
    link,
    shield,
    stepDone,
    stepRetry,
};

export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 24, className }: { name: IconName; size?: number; className?: string }) {
    return <img src={ICONS[name]} width={size} height={size} alt="" aria-hidden className={className} />;
}
