import Link from "next/link";
import { CavaAIWordmark } from "@/components/CavaAIWordmark";
import NavItems from "@/components/NavItems";
import UserDropdown from "@/components/UserDropdown";
import SearchCommand from "@/components/SearchCommand";

const Header = ({ user, initialStocks }: { user: User, initialStocks: StockWithWatchlistStatus[] }) => {
    return (
        <header className="sticky top-0 header">
            <div className="container header-wrapper">
                <Link href="/" prefetch={false} className="flex items-center justify-center gap-2">
                    <CavaAIWordmark />
                </Link>

                {/* Buscador visible */}
                <div className="flex-1 max-w-md mx-4">
                    <SearchCommand
                        renderAs="button"
                        label="🔍 Buscar acciones... (Ctrl+K)"
                        initialStocks={initialStocks}
                    />
                </div>

                <nav className="hidden sm:block">
                    <NavItems initialStocks={initialStocks} />
                </nav>

                <UserDropdown user={user} initialStocks={initialStocks} />
            </div>
        </header>
    )
}
export default Header
