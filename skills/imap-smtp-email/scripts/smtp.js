#!/usr/bin/env node

/**
 * SMTP Email CLI
 * Send email via SMTP protocol. Works with Gmail, Outlook, 163.com, and any standard SMTP server.
 * Supports attachments, HTML content, and multiple recipients.
 */

const nodemailer = require('nodemailer');
const path = require('path');
const os = require('os');
const fs = require('fs');
require('dotenv').config({ path: path.resolve(__dirname, '../.env') });

function validateReadPath(inputPath) {
  let realPath;
  try {
    realPath = fs.realpathSync(inputPath);
  } catch {
    realPath = path.resolve(inputPath);
  }

  const allowedDirsStr = process.env.ALLOWED_READ_DIRS;
  if (!allowedDirsStr) {
    throw new Error('ALLOWED_READ_DIRS not set in .env. File read operations are disabled.');
  }

  const allowedDirs = allowedDirsStr.split(',').map(d =>
    path.resolve(d.trim().replace(/^~/, os.homedir()))
  );

  const allowed = allowedDirs.some(dir =>
    realPath === dir || realPath.startsWith(dir + path.sep)
  );

  if (!allowed) {
    throw new Error(`Access denied: '${inputPath}' is outside allowed read directories`);
  }

  return realPath;
}

// Parse command-line arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const command = args[0];
  const options = {};
  const positional = [];

  for (let i = 1; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const value = args[i + 1];
      options[key] = value || true;
      if (value && !value.startsWith('--')) i++;
    } else {
      positional.push(arg);
    }
  }

  return { command, options, positional };
}

// Create SMTP transporter
function createTransporter() {
  const config = {
    host: process.env.SMTP_HOST,
    port: parseInt(process.env.SMTP_PORT) || 587,
    secure: process.env.SMTP_SECURE === 'true', // true for 465, false for other ports
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
    tls: {
      rejectUnauthorized: process.env.SMTP_REJECT_UNAUTHORIZED !== 'false',
    },
  };

  if (!config.host || !config.auth.user || !config.auth.pass) {
    throw new Error('Missing SMTP configuration. Please set SMTP_HOST, SMTP_USER, and SMTP_PASS in .env');
  }

  return nodemailer.createTransport(config);
}

// Send email
async function sendEmail(options) {
  const transporter = createTransporter();

  // Verify connection
  try {
    await transporter.verify();
    console.error('SMTP server is ready to send');
  } catch (err) {
    throw new Error(`SMTP connection failed: ${err.message}`);
  }

  const mailOptions = {
    from: options.from || process.env.SMTP_FROM || process.env.SMTP_USER,
    to: options.to,
    cc: options.cc || undefined,
    bcc: options.bcc || undefined,
    subject: options.subject || '(no subject)',
    text: options.text || undefined,
    html: options.html || undefined,
    attachments: options.attachments || [],
  };

  // If neither text nor html provided, use default text
  if (!mailOptions.text && !mailOptions.html) {
    mailOptions.text = options.body || '';
  }

  const info = await transporter.sendMail(mailOptions);

  return {
    success: true,
    messageId: info.messageId,
    response: info.response,
    to: mailOptions.to,
  };
}

// Read file content for attachments
function readAttachment(filePath) {
  validateReadPath(filePath);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Attachment file not found: ${filePath}`);
  }
  return {
    filename: path.basename(filePath),
    path: path.resolve(filePath),
  };
}

// Send email with file content
async function sendEmailWithContent(options) {
  // Handle attachments
  if (options.attach) {
    const attachFiles = options.attach.split(',').map(f => f.trim());
    options.attachments = attachFiles.map(f => readAttachment(f));
  }

  return await sendEmail(options);
}

// Test SMTP connection
async function testConnection() {
  const transporter = createTransporter();

  try {
    await transporter.verify();
    const info = await transporter.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to: process.env.SMTP_USER, // Send to self
      subject: 'SMTP Connection Test',
      text: 'This is a test email from the IMAP/SMTP email skill.',
      html: '<p>This is a <strong>test email</strong> from the IMAP/SMTP email skill.</p>',
    });

    return {
      success: true,
      message: 'SMTP connection successful',
      messageId: info.messageId,
    };
  } catch (err) {
    throw new Error(`SMTP test failed: ${err.message}`);
  }
}

// Extract first email address from a string (e.g. user message).
function extractEmailFromMessage(text) {
  if (!text || typeof text !== 'string') return null;
  const match = text.match(/[\w.-]+@[\w.-]+\.\w+/);
  return match ? match[0].trim() : null;
}

// Extract the intended email content from a natural-language request, so we don't send the full meta sentence as the body.
// E.g. "能帮我给a@b.com发封邮件，告诉他xxx" -> "xxx"; "send email to a@b.com saying hello" -> "hello"
function extractBodyFromMessage(fullMessage) {
  const msg = (fullMessage || '').trim();
  // Chinese: "告诉他/说/内容(：|:)? ..." or "发邮件...告诉他..." -> take the part after the verb
  const cnTell = msg.match(/(?:告诉(?:他|她|他们)?|说|写|内容)[:：]\s*(.+)/s);
  if (cnTell && cnTell[1]) return cnTell[1].trim();
  const cnAfter = msg.match(/(?:发(?:封)?邮件[，,]?\s*)?(?:告诉(?:他|她|他们)|说)\s*(.+?)(?:\s*[。.]|$)/s);
  if (cnAfter && cnAfter[1]) return cnAfter[1].trim();
  // English: "say(ing)? ..." or "tell him/her ..." or "message: ..."
  const enSay = msg.match(/(?:say(?:ing)?|tell\s+(?:him|her|them)|message)\s*[:：]?\s*(.+)/is);
  if (enSay && enSay[1]) return enSay[1].trim();
  // Fallback: if message contains an email, use the part after the email as body (e.g. "给 a@b.com 发邮件，xxx" -> "xxx")
  const to = extractEmailFromMessage(msg);
  if (to) {
    const idx = msg.indexOf(to);
    const after = msg.substring(idx + to.length).replace(/^[\s，,、：:]+/, '').trim();
    if (after.length > 0) return after;
  }
  return msg;
}

// Parse natural-language send request (e.g. "能帮我给a@b.com发封邮件，告诉他xxx") -> { to, body, subject }.
function parseSendFromMessage(fullMessage) {
  const msg = (fullMessage || '').trim();
  const to = extractEmailFromMessage(msg);
  const body = extractBodyFromMessage(msg);
  if (!to) return { to: null, body: msg, subject: 'Message from HomeClaw' };
  return { to, body: body || msg, subject: 'Message from HomeClaw' };
}

// Main CLI handler
async function main() {
  let { command, options, positional } = parseArgs();
  // When run_skill is called with no args, Core sets HOMECLAW_USER_MESSAGE to the user's text; treat as send-from-message.
  if ((command === undefined || command === '') && process.env.HOMECLAW_USER_MESSAGE) {
    command = 'send-from-message';
    positional = [process.env.HOMECLAW_USER_MESSAGE];
  }

  try {
    let result;

    switch (command) {
      case 'send-from-message': {
        const rawMessage = positional[0] || options.body || options.message || '';
        const { to, body, subject } = parseSendFromMessage(rawMessage);
        if (!to) {
          throw new Error('No email address found in message. Include an address like user@example.com');
        }
        result = await sendEmailWithContent({ to, subject, body });
        break;
      }
      case 'send':
        if (!options.to) {
          throw new Error('Missing required option: --to <email>');
        }
        if (!options.subject && !options['subject-file']) {
          throw new Error('Missing required option: --subject <text> or --subject-file <file>');
        }

        // Read subject from file if specified
        if (options['subject-file']) {
          validateReadPath(options['subject-file']);
          options.subject = fs.readFileSync(options['subject-file'], 'utf8').trim();
        }

        // Read body from file if specified
        if (options['body-file']) {
          validateReadPath(options['body-file']);
          const content = fs.readFileSync(options['body-file'], 'utf8');
          if (options['body-file'].endsWith('.html') || options.html) {
            options.html = content;
          } else {
            options.text = content;
          }
        } else if (options['html-file']) {
          validateReadPath(options['html-file']);
          options.html = fs.readFileSync(options['html-file'], 'utf8');
        } else if (options.body) {
          options.text = options.body;
        }

        result = await sendEmailWithContent(options);
        break;

      case 'test':
        result = await testConnection();
        break;

      default:
        console.error('Unknown command:', command);
        console.error('Available commands: send, send-from-message, test');
        console.error('\nUsage:');
        console.error('  send   --to <email> --subject <text> [--body <text>] [--html] [--cc <email>] [--bcc <email>] [--attach <file>]');
        console.error('  send-from-message <natural language>  Extract email from message and send (e.g. "给 user@example.com 发邮件，告诉他 ...")');
        console.error('  test   Test SMTP connection');
        process.exit(1);
    }

    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

main();
