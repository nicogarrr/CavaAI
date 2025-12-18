
import dotenv from 'dotenv';
dotenv.config();

// Mock env for testing
process.env.BETTER_AUTH_SECRET = process.env.BETTER_AUTH_SECRET || "mock-secret-for-debugging-purposes-only-32-chars";


async function main() {
    console.log("Checking environment...");
    console.log("FINNHUB_API_KEY:", process.env.FINNHUB_API_KEY ? "Present" : "Missing");

    // Dynamic import to ensure env is loaded
    const { generateProPicks } = await import('../lib/actions/proPicks.actions');

    console.log("Starting debug of generateProPicks...");
    try {
        const picks = await generateProPicks(10);
        console.log(`Result count: ${picks.length}`);
        if (picks.length === 0) {
            console.log("No picks returned.");
        } else {
            console.log("Top pick snippet:");
            console.log(JSON.stringify(picks[0], null, 2));

            console.log("Scores overview:", picks.map(p => `${p.symbol}: ${p.score}`).join(', '));
        }
    } catch (error) {
        console.error("Fatal error:", error);
    }
}

main();
