import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Building2, Globe, MapPin, Phone } from 'lucide-react';
import Link from 'next/link';

interface StockProfileProps {
    profile: any;
}

export default function StockProfile({ profile }: StockProfileProps) {
    if (!profile) {
        return (
            <Card className="bg-gray-800/50 border-gray-700 h-full">
                <CardContent className="flex items-center justify-center h-full text-gray-500">
                    No hay información de perfil disponible.
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-gray-800/50 border-gray-700">
            <CardHeader>
                <CardTitle className="text-gray-100 flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-teal-400" />
                    Perfil de la Empresa
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                    {profile.finnhubIndustry && (
                        <Badge variant="secondary" className="bg-blue-900/30 text-blue-300 border-blue-800">
                            {profile.finnhubIndustry}
                        </Badge>
                    )}
                    {profile.exchange && (
                        <Badge variant="outline" className="border-gray-600 text-gray-400">
                            {profile.exchange}
                        </Badge>
                    )}
                    {profile.currency && (
                        <Badge variant="outline" className="border-gray-600 text-gray-400">
                            {profile.currency}
                        </Badge>
                    )}
                </div>

                <div className="grid grid-cols-1 gap-3 text-sm">
                    {profile.country && (
                        <div className="flex items-center gap-2 text-gray-300">
                            <MapPin className="h-4 w-4 text-gray-500" />
                            <span>{profile.country}</span>
                        </div>
                    )}
                    {profile.weburl && (
                        <Link
                            href={profile.weburl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors"
                        >
                            <Globe className="h-4 w-4" />
                            <span>Visitar sitio web</span>
                        </Link>
                    )}
                    {profile.phone && (
                        <div className="flex items-center gap-2 text-gray-300">
                            <Phone className="h-4 w-4 text-gray-500" />
                            <span>{profile.phone}</span>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
