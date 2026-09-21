import Link from "next/link";
import { CavaAIWordmark } from "@/components/CavaAIWordmark";
import UserDropdown from "@/components/UserDropdown";
import SearchCommand from "@/components/SearchCommand";
import MobileNav from "@/components/MobileNav";

const Header = ({ user, initialStocks }: { user: User, initialStocks: StockWithWatchlistStatus[] }) => {
    return (
        <header className="sticky top-0 header max-sm:h-auto">
            <div className="container header-wrapper flex-wrap gap-x-2 gap-y-2 px-4 sm:px-6">
                <div className="flex min-w-0 items-center gap-1">
                    <MobileNav initialStocks={initialStocks} />
                    <Link href="/" prefetch={false} className="flex min-h-[44px] items-center justify-center gap-2">
                        <CavaAIWordmark />
                    </Link>
                </div>

                {/* Buscador: fila propia a full-width en móvil, inline desde sm */}
                <div className="order-3 w-full min-w-0 sm:order-2 sm:mx-4 sm:w-auto sm:max-w-md sm:flex-1">
                    <SearchCommand
                        renderAs="button"
                        label="🔍 Buscar acciones... (Ctrl+K)"
                        initialStocks={initialStocks}
                    />
                </div>


                <div className="order-2 ml-auto flex items-center sm:order-3 sm:ml-0">
                    <UserDropdown user={user} initialStocks={initialStocks} />
                </div>
            </div>
        </header>
    )
}
export default Header
