const https = require('https');
const fs = require('fs');
const path = require('path');

// Simple dotenv parser
try {
    const envPath = path.resolve(process.cwd(), '.env');
    if (fs.existsSync(envPath)) {
        const envConfig = fs.readFileSync(envPath, 'utf8');
        envConfig.split('\n').forEach(line => {
            const [key, value] = line.split('=');
            if (key && value) {
                process.env[key.trim()] = value.trim();
            }
        });
    }
} catch (e) {
    console.error("Error loading .env", e);
}

const apiKey = process.env.GEMINI_API_KEY;

if (!apiKey) {
    console.error("❌ CRTICIAL: No GEMINI_API_KEY found in .env");
    process.exit(1);
}

const url = `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`;

https.get(url, (res) => {
    let data = '';
    res.on('data', (chunk) => data += chunk);
    res.on('end', () => {
        try {
            const json = JSON.parse(data);
            if (json.error) {
                console.error("❌ API Error:", json.error.message);
            } else if (json.models) {
                console.log("\n✅ AVAILABLE MODELS FOR YOUR KEY:");
                json.models.forEach(m => {
                    // Filter for 'gemini' models to keep it clean
                    if (m.name.includes('gemini')) {
                        console.log(`- ${m.name.replace('models/', '')}`);
                    }
                });
            } else {
                console.log("Unknown response:", json);
            }
        } catch (e) {
            console.error("Parse error:", e);
        }
    });
}).on("error", (err) => {
    console.log("Error: " + err.message);
});
