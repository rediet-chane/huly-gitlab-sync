// huly_api.js - MCP bridge from Node to Huly via @firfi/huly-mcp
//
// Two modes:
//   node huly_api.js --list-projects
//       -> Lists every Huly project in your workspace, with its "identifier"
//          (a short code like "HULY", NOT the display name). Run this once,
//          then put the right identifier in .env as HULY_PROJECT_IDENTIFIER.
//
//   node huly_api.js "<title>" "<description>" [status]
//       -> Actually creates the issue in Huly.
//          Exit code 0 = success, 1 = failure (this is what main.py checks).

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load .env from the project root (same folder as this script)
dotenv.config({ path: resolve(__dirname, '.env') });

const HULY_EMAIL = process.env.HULY_EMAIL;
const HULY_PASSWORD = process.env.HULY_PASSWORD;
const HULY_WORKSPACE = process.env.HULY_WORKSPACE;
const HULY_URL = process.env.HULY_URL || 'https://huly.app';
const HULY_PROJECT_IDENTIFIER = process.env.HULY_PROJECT_IDENTIFIER;

/**
 * Opens an MCP connection to the @firfi/huly-mcp server (spawned via npx),
 * runs `fn(client)`, then always closes the connection.
 */
async function withHulyClient(fn) {
    if (!HULY_EMAIL || !HULY_PASSWORD || !HULY_WORKSPACE) {
        console.error('❌ Missing HULY_EMAIL, HULY_PASSWORD or HULY_WORKSPACE in .env');
        process.exit(1);
    }

    const transport = new StdioClientTransport({
        command: 'npx',
        args: ['-y', '@firfi/huly-mcp@latest'],
        env: {
            HULY_URL,
            HULY_EMAIL,
            HULY_PASSWORD,
            HULY_WORKSPACE,
            NODE_ENV: 'production',
        },
    });

    const client = new Client({ name: 'huly-gitlab-sync', version: '1.0.0' });

    console.error('🔗 Connecting to Huly MCP server...');
    await client.connect(transport);
    console.error('✅ Connected to Huly MCP server');

    try {
        return await fn(client);
    } finally {
        await client.close();
        console.error('🔌 Disconnected from Huly.');
    }
}

function firstText(result) {
    const block = result.content?.find((c) => c.type === 'text');
    return block ? block.text : '';
}

async function listProjects() {
    await withHulyClient(async (client) => {
        // THE FIX: callTool(), not request({...}, {}).
        // client.request() needs a Zod result schema as its 2nd argument —
        // passing {} there isn't valid, which is why this silently/loudly
        // failed before. callTool() is the SDK's purpose-built wrapper for
        // exactly "call this tool with these arguments".
        const result = await client.callTool({ name: 'list_projects', arguments: {} });

        if (result.isError) {
            console.error('❌ list_projects failed:', firstText(result));
            process.exit(1);
        }

        console.log(JSON.stringify(result.structuredContent ?? firstText(result), null, 2));
    });
}

async function createHulyIssue(title, description, status) {
    if (!HULY_PROJECT_IDENTIFIER) {
        console.error('❌ HULY_PROJECT_IDENTIFIER is not set in .env.');
        console.error('   Run "node huly_api.js --list-projects" first to find it.');
        process.exit(1);
    }

    await withHulyClient(async (client) => {
        const fullDescription = `${description || ''}\n\n---\n**Source**: GitLab Sync\n**Synced**: ${new Date().toISOString()}`;

        console.error(`📝 Creating issue in project "${HULY_PROJECT_IDENTIFIER}": "${title}"`);

        // create_issue requires { project, title }; description/status are
        // optional but we always want to set them. (Verified against the
        // actual CreateIssueParamsSchema in node_modules/@firfi/huly-mcp.)
        const result = await client.callTool({
            name: 'create_issue',
            arguments: {
                project: HULY_PROJECT_IDENTIFIER,
                title,
                description: fullDescription,
                status,
            },
        });

        if (result.isError) {
            // Tool-level errors (e.g. unknown status name for this project's
            // workflow) come back here, not as a thrown exception.
            console.error('❌ Huly rejected the issue:', firstText(result));
            process.exit(1);
        }

        // The old code read result.result.content[...] — callTool() returns
        // the result directly, there's no outer .result wrapper.
        const identifier = result.structuredContent?.identifier ?? firstText(result);

        console.log(identifier); // stdout: the one line main.py reads back
        console.error(`✅ Created ${identifier} — ${HULY_URL}/workbench/${HULY_WORKSPACE}`);
    });
}

const args = process.argv.slice(2);

if (args[0] === '--list-projects') {
    listProjects()
        .then(() => process.exit(0))
        .catch((err) => {
            console.error('Unhandled error:', err.message || err);
            process.exit(1);
        });
} else if (args.length < 2) {
    console.error('Usage:');
    console.error('  node huly_api.js --list-projects');
    console.error('  node huly_api.js "<title>" "<description>" [status]');
    process.exit(1);
} else {
    const [title, description, status = 'Todo'] = args;
    createHulyIssue(title, description, status)
        .then(() => process.exit(0))
        .catch((err) => {
            console.error('Unhandled error:', err.message || err);
            process.exit(1);
        });
}