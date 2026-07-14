const { exec } = require('child_process');
const dotenv = require('dotenv');
const path = require('path');

dotenv.config({ path: path.join(__dirname, '.env') });

async function createHulyIssue(title, description, status = 'Todo') {
    const email = process.env.HULY_EMAIL;
    const password = process.env.HULY_PASSWORD;
    const workspace = process.env.HULY_WORKSPACE;
    const token = process.env.HULY_TOKEN;

    console.error(`📧 Email: ${email}`);
    console.error(`📂 Workspace: ${workspace}`);

    const escapedTitle = title.replace(/"/g, '\\"').replace(/\n/g, ' ');
    const escapedDescription = description.replace(/"/g, '\\"').replace(/\n/g, ' ');

    // Build the command
    let cmd;
    if (token) {
        cmd = `npx -y @bgx4k3p/huly-mcp-server create-issue --title "${escapedTitle}" --description "${escapedDescription}" --workspace ${workspace} --token ${token}`;
    } else {
        cmd = `npx -y @bgx4k3p/huly-mcp-server create-issue --title "${escapedTitle}" --description "${escapedDescription}" --workspace ${workspace} --email ${email} --password ${password}`;
    }

    console.error(`🔧 Running command...`);
    console.error(`📝 Title: ${title.substring(0, 50)}...`);

    return new Promise((resolve, reject) => {
        exec(cmd, { 
            maxBuffer: 1024 * 1024,
            timeout: 60000,
            shell: true
        }, (error, stdout, stderr) => {
            if (error) {
                console.error('❌ CLI Error:', error.message);
                if (stderr) console.error('stderr:', stderr.substring(0, 300));
                reject(error);
                return;
            }
            if (stdout) console.log(stdout);
            if (stderr) console.error('⚠️', stderr.substring(0, 200));
            resolve(true);
        });
    });
}

const args = process.argv.slice(2);
if (args.length < 2) {
    console.error('Usage: node huly_cli_bridge.js "Issue Title" "Issue Description" [Status]');
    console.error('Example: node huly_cli_bridge.js "My Issue" "This is a test" Todo');
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