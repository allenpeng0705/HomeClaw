/**
 * HomeClaw WhatsApp Web bridge.
 * Connects to WhatsApp via Baileys, receives messages, POSTs to the whatsappweb
 * channel /webhook, and sends the response back to WhatsApp.
 *
 * Env:
 *   CHANNEL_URL - Base URL of the whatsappweb channel (e.g. http://127.0.0.1:8010)
 *   AUTH_DIR    - Directory for Baileys auth state (default: ./auth)
 *
 * First run: scan QR code in terminal. Session is saved in AUTH_DIR.
 */

import makeWASocket from "@whiskeysockets/baileys";
import { useMultiFileAuthState } from "@whiskeysockets/baileys";
import pino from "pino";
import axios from "axios";
import path from "path";
import fs from "fs";

const CHANNEL_URL = (process.env.CHANNEL_URL || "http://127.0.0.1:8010").replace(/\/$/, "");
const AUTH_DIR = process.env.AUTH_DIR || path.join(process.cwd(), "auth");

// Ensure auth dir exists
if (!fs.existsSync(AUTH_DIR)) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
}

const logger = pino({ level: "info" });

function toJid(chatId) {
  if (typeof chatId === "string") return chatId;
  if (chatId?.id) return `${chatId.id}@${chatId.server || "s.whatsapp.net"}`;
  return null;
}

function extractTextFromMessage(msg) {
  if (!msg) return "";
  const m = msg.message || msg;
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    m.documentMessage?.caption ||
    ""
  ).trim();
}

async function sendToChannel(userId, text, options = {}) {
  const url = `${CHANNEL_URL}/webhook`;
  try {
    const { data } = await axios.post(
      url,
      {
        user_id: userId,
        text: text || "(no text)",
        channel_name: "whatsappweb",
        ...options,
      },
      { timeout: 120000 }
    );
    return data?.text ?? "";
  } catch (err) {
    const msg = err.response?.data?.error || err.message;
    logger.error({ err: msg }, "Channel POST failed");
    return `[Error: ${msg}]`;
  }
}

async function main() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: true,
    logger,
  });

  sock.ev.on("connection.update", (update) => {
    const { connection, qr } = update;
    if (connection === "open") {
      logger.info("WhatsApp connected");
    }
    if (connection === "close") {
      logger.warn("WhatsApp disconnected");
    }
    if (qr) {
      logger.info("Scan the QR code above with WhatsApp (Linked devices)");
    }
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      const jid = toJid(m.key?.remoteJid);
      if (!jid || jid === "status@broadcast") continue;
      const text = extractTextFromMessage(m);
      if (!text) continue;
      const fromMe = m.key?.fromMe;
      if (fromMe) continue;

      const userId = jid;
      logger.info({ jid, text: text.slice(0, 50) }, "Incoming message");
      const reply = await sendToChannel(userId, text);
      if (reply) {
        try {
          await sock.sendMessage(jid, { text: reply });
        } catch (e) {
          logger.error({ err: e.message }, "Send reply failed");
        }
      }
    }
  });

  logger.info({ CHANNEL_URL, AUTH_DIR }, "Bridge running; waiting for WhatsApp messages");
}

main().catch((e) => {
  logger.fatal(e, "Bridge failed");
  process.exit(1);
});
