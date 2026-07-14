import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import { existsSync } from 'fs';  // <-- ADD THIS

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

dotenv.config({ path: resolve(__dirname, '.env') });

const HULY_EMAIL              = process.env.HULY_EMAIL;
const HULY_PASSWORD           = process.env.HULY_PASSWORD;
const HULY_WORKSPACE          = process.env.HULY_WORKSPACE;
const HULY_URL                = process.env.HULY_URL || 'https://huly.app';
const HULY_PROJECT_IDENTIFIER = process.env.HULY_PROJECT_IDENTIFIER;

const MCP_PATHS = [
    resolve(__dirname, 'node_modules', '@firfi', 'huly-mcp', 'dist', 'index.cjs'),
    resolve(__dirname, 'node_modules', '@firfi', 'huly-mcp', 'dist', 'index.js'),
];
let HULY_MCP_BIN = MCP_PATHS.find(p => existsSync(p));  // <-- FIXED

if (!HULY_MCP_BIN) {
    console.error('❌ Could not find @firfi/huly-mcp in node_modules');
    console.error('   Run: npm install @firfi/huly-mcp@latest');
    process.exit(1);
}

process.on('uncaughtException',    (err) => { console.error('❌ Uncaught:', err.message); process.exit(1); });
process.on('unhandledRejection', (reason) => { console.error('❌ Unhandled:', reason);    process.exit(1); });

async function withHulyClient(fn) {
    if (!HULY_EMAIL || !HULY_PASSWORD || !HULY_WORKSPACE) {
        console.error('❌ Missing HULY_EMAIL, HULY_PASSWORD, or HULY_WORKSPACE in .env');
        process.exit(1);
    }

    const transport = new StdioClientTransport({
        command: 'node',
        args: [HULY_MCP_BIN],
        env: { HULY_URL, HULY_EMAIL, HULY_PASSWORD, HULY_WORKSPACE, NODE_ENV: 'production' },
    });

    const client = new Client({ name: 'huly-gitlab-sync', version: '1.0.0' });

    console.error('🔗 Connecting to Huly...');
    await client.connect(transport);
    console.error('✅ Connected');

    try {
        return await fn(client);
    } finally {
        await client.close();
        console.error('🔌 Disconnected');
    }
}

function firstText(result) {
    return result.content?.find((c) => c.type === 'text')?.text ?? '';
}

async function listProjects() {
    await withHulyClient(async (client) => {
        const result = await client.callTool({ name: 'list_projects', arguments: {} });
        if (result.isError) { console.error('❌', firstText(result)); process.exit(1); }
        console.log(JSON.stringify(result.structuredContent ?? firstText(result), null, 2));
    });
}

async function listIssues() {
    if (!HULY_PROJECT_IDENTIFIER) {
        console.error('❌ HULY_PROJECT_IDENTIFIER not set in .env');
        process.exit(1);
    }
    await withHulyClient(async (client) => {
        const result = await client.callTool({
            name: 'list_issues',
            arguments: { project: HULY_PROJECT_IDENTIFIER },
        });
        if (result.isError) { console.error('❌', firstText(result)); process.exit(1); }
        const issues = result.structuredContent ?? JSON.parse(firstText(result) || '[]');
        console.log(JSON.stringify(issues));
    });
}

async function createIssue(title, description, status) {
    if (!HULY_PROJECT_IDENTIFIER) {
        console.error('❌ HULY_PROJECT_IDENTIFIER not set. Run: node huly_api.js --list-projects');
        process.exit(1);
    }
    await withHulyClient(async (client) => {
        const fullDesc = `${description || ''}\n\n---\n**Source**: GitLab Sync\n**Synced**: ${new Date().toISOString()}`;
        console.error(`📝 Creating "${title}" in project ${HULY_PROJECT_IDENTIFIER}`);

        const result = await client.callTool({
            name: 'create_issue',
            arguments: { project: HULY_PROJECT_IDENTIFIER, title, description: fullDesc, status },
        });

        if (result.isError) { console.error('❌ Huly rejected the issue:', firstText(result)); process.exit(1); }

        const identifier = result.structuredContent?.identifier ?? firstText(result);
        console.log(identifier);
        console.error(`✅ Created: ${identifier}`);
    });
}

const args = process.argv.slice(2);
const run = args[0] === '--list-projects' ? listProjects
          : args[0] === '--list-issues'   ? listIssues
          : args.length >= 2              ? () => createIssue(args[0], args[1], args[2] ?? 'Todo')
          : null;

if (!run) {
    console.error('Usage:');
    console.error('  node huly_api.js --list-projects');
    console.error('  node huly_api.js --list-issues');
    console.error('  node huly_api.js "<title>" "<description>" [status]');
    process.exit(1);
}

run().then(() => process.exit(0)).catch((err) => { console.error('❌', err.message || err); process.exit(1); });