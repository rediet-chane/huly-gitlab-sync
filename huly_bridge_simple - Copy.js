import { exec } from 'child_process';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

dotenv.config({ path: resolve(__dirname, '.env') });

async function createHulyIssue(title, description, status) {
    const email = process.env.HULY_EMAIL;
    const password = process.env.HULY_PASSWORD;
    const workspace = process.env.HULY_WORKSPACE;
    const token = process.env.HULY_TOKEN;

    console.error(`📧 Email: ${email}`);
    console.error(`📂 Workspace: ${workspace}`);

    const escapedTitle = title.replace(/"/g, '\\"').replace(/\n/g, ' ');
    const escapedDescription = description.replace(/"/g, '\\"').replace(/\n/g, ' ');

    let cmd;
    if (token) {
        cmd = `npx -y @bgx4k3p/huly-mcp-server create-issue --title "${escapedTitle}" --description "${escapedDescription}" --workspace ${workspace} --token ${token}`;
    } else {
        cmd = `npx -y @bgx4k3p/huly-mcp-server create-issue --title "${escapedTitle}" --description "${escapedDescription}" --workspace ${workspace} --email ${email} --password ${password}`;
    }

    console.error(`🔧 Running: npx -y @bgx4k3p/huly-mcp-server create-issue ...`);

    return new Promise((resolve, reject) => {
        exec(cmd, { 
            maxBuffer: 1024 * 1024,
            timeout: 120000,
            shell: true
        }, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ CLI Error:', error.message);
                if (stderr) console.error('stderr:', stderr.substring(0, 300));
                reject(error);
                return;
            }
            // Parse the output to get the issue ID
            const match = stdout.match(/identifier["\s:]+([A-Z0-9-]+)/);
            const identifier = match ? match[1] : 'unknown';
            console.log(identifier);
            resolve(true);
        });
    });
}

const args = process.argv.slice(2);
if (args.length < 2) {
    console.error('Usage: node huly_bridge_simple.js "Issue Title" "Issue Description" [Status]');
    process.exit(1);
}

const title = args[0];
const description = args[1];
const status = args[2] || 'Todo';

console.error(`🚀 Starting Huly CLI bridge...`);

createHulyIssue(title, description, status)
    .then(() => {
        console.error('✅ Issue created successfully!');
        process.exit(0);
    })
    .catch((error) => {
        console.error('❌ Failed:', error.message);
        process.exit(1);
    });