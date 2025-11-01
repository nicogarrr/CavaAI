import { getUserPortfolios } from '@/lib/actions/portfolio.actions';
import PortfolioList from '@/components/portfolio/PortfolioList';
import CreatePortfolioButton from '@/components/portfolio/CreatePortfolioButton';
import { redirect } from 'next/navigation';

export default async function PortfolioPage() {
    const portfolios = await getUserPortfolios();

    // Si solo hay una cartera, redirigir automáticamente a ella
    if (portfolios && portfolios.length === 1) {
        redirect(`/portfolio/${portfolios[0]._id}`);
    }

    return (
        <div className="flex min-h-screen flex-col p-6">
            <div className="mb-8">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h1 className="text-3xl font-bold">Mis Carteras</h1>
                        <p className="text-muted-foreground mt-2">
                            Gestiona tus carteras de inversión y analiza su rendimiento
                        </p>
                    </div>
                    <CreatePortfolioButton />
                </div>
            </div>

            <PortfolioList portfolios={portfolios} />
        </div>
    );
}

