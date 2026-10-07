import Link from 'next/link';
import { CavaAIWordmark } from '@/components/CavaAIWordmark';
import UserDropdown from '@/components/UserDropdown';
import SearchCommand from '@/components/SearchCommand';
import MobileNav from '@/components/MobileNav';
import { Bell } from 'lucide-react';

/**
 * Cabecera de una sola fila en TODOS los viewports. Antes el buscador ocupaba
 * una segunda fila a full-width por debajo de sm, dejando ~112px de chrome
 * sticky permanente en movil; ahora por debajo de sm solo hay un icono de lupa
 * que abre el mismo dialogo (Ctrl+K y "/" tambien lo abren).
 */
const Header = ({ user, initialStocks }: { user: User; initialStocks?: StockWithWatchlistStatus[] }) => {
    return (
        <header className="header">
            {/* El padding horizontal vive unicamente en `.container`; antes se
                sumaba tres veces (container + header-wrapper + px-4 sm:px-6). */}
            <div className="container header-wrapper">
                <div className="flex min-w-0 shrink-0 items-center gap-1">
                    <MobileNav initialStocks={initialStocks} />
                    <Link href="/inicio" prefetch={false} className="flex min-h-11 items-center justify-center gap-2">
                        <CavaAIWordmark />
                    </Link>
                </div>

                <div className="mx-auto hidden min-w-0 flex-1 sm:flex sm:max-w-xl">
                    <SearchCommand renderAs="button" initialStocks={initialStocks} />
                </div>

                <div className="ml-auto flex shrink-0 items-center gap-1">
                    <div className="sm:hidden">
                        <SearchCommand
                            renderAs="icon"
                            initialStocks={initialStocks}
                        />
                    </div>
                    <Link href="/alerts" aria-label="Alertas" title="Alertas" className="flex h-11 w-11 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-800 hover:text-teal-300"><Bell aria-hidden="true" className="h-5 w-5" /></Link>
                    <UserDropdown user={user} />
                </div>
            </div>
        </header>
    )
}
export default Header
