"use client";
import React, { useMemo, useState } from "react";
import { addToWatchlist, removeFromWatchlist } from "@/lib/actions/watchlist.actions";
import { Loader2 } from "lucide-react";

interface WatchlistButtonProps {
    symbol: string;
    company?: string;
    isInWatchlist?: boolean;
    showTrashIcon?: boolean;
    type?: "button" | "icon";
    onWatchlistChange?: (symbol: string, added: boolean) => void;
}

const WatchlistButton = ({
    symbol,
    company,
    isInWatchlist,
    showTrashIcon = false,
    type = "button",
    onWatchlistChange,
}: WatchlistButtonProps) => {
    const [added, setAdded] = useState<boolean>(!!isInWatchlist);
    const [loading, setLoading] = useState(false);

    const label = useMemo(() => {
        if (type === "icon") return added ? "" : "";
        return added ? "Remove from Watchlist" : "Add to Watchlist";
    }, [added, type]);

    const handleClick = async (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();

        if (loading) return;
        setLoading(true);

        const next = !added;
        setAdded(next); // Optimistic update

        try {
            if (next) {
                await addToWatchlist(symbol, company || symbol);
            } else {
                await removeFromWatchlist(symbol);
            }
            onWatchlistChange?.(symbol, next);
        } catch (error) {
            console.error("Error updating watchlist", error);
            setAdded(!next); // Revert on error
        } finally {
            setLoading(false);
        }
    };

    if (type === "icon") {
        return (
            <button
                title={added ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
                aria-label={added ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
                className={`watchlist-icon-btn ${added ? "watchlist-icon-added" : ""}`}
                onClick={handleClick}
                disabled={loading}
            >
                {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                ) : (
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill={added ? "#FACC15" : "none"}
                        stroke={added ? "#FACC15" : "currentColor"}
                        strokeWidth="1.5"
                        className="watchlist-star w-6 h-6"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.385a.563.563 0 00-.182-.557L3.04 10.385a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345l2.125-5.111z"
                        />
                    </svg>
                )}
            </button>
        );
    }

    return (
        <button
            className={`watchlist-btn ${added ? "watchlist-remove" : ""} flex items-center gap-2 px-4 py-2 rounded-lg transition-colors font-medium border ${added
                ? "bg-red-500/10 border-red-500/50 text-red-500 hover:bg-red-500/20"
                : "bg-teal-500/10 border-teal-500/50 text-teal-400 hover:bg-teal-500/20"
                }`}
            onClick={handleClick}
            aria-pressed={added}
            aria-label={added ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
            type="button"
            disabled={loading}
        >
            {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
                <>
                    {showTrashIcon && added ? (
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={1.5}
                            stroke="currentColor"
                            className="w-4 h-4"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 4v6m4-6v6m4-6v6" />
                        </svg>
                    ) : null}
                    <span>{label}</span>
                </>
            )}
        </button>
    );
};

export default WatchlistButton;