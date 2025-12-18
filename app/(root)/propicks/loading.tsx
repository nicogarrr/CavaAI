import { Skeleton } from "@/components/ui/skeleton"
import { Sparkles, TrendingUp } from "lucide-react"
import { Card } from "@/components/ui/card"

export default function Loading() {
    return (
        <div className="flex min-h-screen flex-col p-6 space-y-6">
            {/* Header Loading State */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                    <Skeleton className="h-8 w-8 rounded-full bg-gray-700" />
                    <div className="space-y-2">
                        <Skeleton className="h-8 w-64 bg-gray-700" />
                        <Skeleton className="h-4 w-96 bg-gray-700" />
                    </div>
                </div>
            </div>

            {/* Tabs Loading State */}
            <div className="space-y-6">
                <div className="flex gap-2 border-b border-gray-700 p-1">
                    <Skeleton className="h-10 w-40 bg-gray-700 rounded-md" />
                    <Skeleton className="h-10 w-40 bg-gray-700 rounded-md" />
                </div>

                {/* Content Loading State */}
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    {/* Sidebar Filters */}
                    <div className="lg:col-span-1 space-y-4">
                        <Skeleton className="h-[400px] w-full bg-gray-800/50 rounded-lg" />
                        <Skeleton className="h-[200px] w-full bg-gray-800/50 rounded-lg" />
                    </div>

                    {/* Results Grid */}
                    <div className="lg:col-span-3 space-y-4">
                        <div className="flex justify-between items-center mb-4">
                            <Skeleton className="h-6 w-32 bg-gray-700" />
                            <Skeleton className="h-6 w-48 bg-gray-700" />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {[1, 2, 3, 4, 5, 6].map((i) => (
                                <Card key={i} className="p-5 border-gray-700 bg-gray-800/50 h-[220px]">
                                    <div className="flex justify-between mb-4">
                                        <div className="space-y-2">
                                            <Skeleton className="h-6 w-24 bg-gray-700" />
                                            <Skeleton className="h-4 w-32 bg-gray-700" />
                                        </div>
                                        <Skeleton className="h-12 w-12 rounded-lg bg-gray-700" />
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 mt-8">
                                        <Skeleton className="h-10 w-full bg-gray-700" />
                                        <Skeleton className="h-10 w-full bg-gray-700" />
                                        <Skeleton className="h-10 w-full bg-gray-700" />
                                    </div>
                                </Card>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
