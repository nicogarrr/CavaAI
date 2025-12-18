
import { generateProPicks } from '../lib/actions/proPicks.actions';

async function main() {
    console.log("Starting debug of generateProPicks...");
    try {
        const picks = await generateProPicks(10);
        console.log(`Result count: ${picks.length}`);
        if (picks.length === 0) {
            console.log("No picks returned.");
        } else {
            console.log("Top pick snippet:");
            console.log(JSON.stringify(picks[0], null, 2));
        }
    } catch (error) {
        console.error("Fatal error:", error);
    }
}

main();
