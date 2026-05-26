import { Bot, Context, Session } from "grammy";
import { run } from "@grammyjs/runner";

interface MySession {
  state: string;
}

type MyContext = Context & Session<MySession>;

const bot = new Bot<MyContext>(process.env.BOT_TOKEN || "your-bot-token");

bot.use(async (ctx, next) => {
  if (!ctx.session) {
    ctx.session = { state: "" };
  }
  await next();
});

bot.command("start", async (ctx) => {
  await ctx.reply(
    "Welcome to Life Data Lake Bot! 📊\n\n" +
    "Available commands:\n" +
    "/today - Get today's summary\n" +
    "/search <query> - Search messages\n" +
    "/weekly - Get weekly review\n" +
    "/stats - View your statistics\n" +
    "/idea - Get a random idea\n" +
    "/help - Show help"
  );
});

bot.command("today", async (ctx) => {
  await ctx.reply("Fetching today's summary...");
  const response = await fetch(`${process.env.API_URL || "http://localhost:8000"}/api/today`);
  if (response.ok) {
    const data = await response.json();
    await ctx.reply(data.content || "No summary available yet.");
  } else {
    await ctx.reply("Unable to fetch summary. Make sure the API is running.");
  }
});

bot.command("search", async (ctx) => {
  const query = ctx.match;
  if (!query) {
    await ctx.reply("Please provide a search query: /search <your query>");
    return;
  }

  await ctx.reply(`Searching for: "${query}"...`);
  const response = await fetch(
    `${process.env.API_URL || "http://localhost:8000"}/api/search?q=${encodeURIComponent(query)}`
  );

  if (response.ok) {
    const results = await response.json();
    if (results.length === 0) {
      await ctx.reply("No results found.");
    } else {
      const formatted = results
        .slice(0, 5)
        .map((r: any, i: number) => `${i + 1}. ${r.text?.slice(0, 100)}... (${r.timestamp})`)
        .join("\n");
      await ctx.reply(`Found ${results.length} results:\n\n${formatted}`);
    }
  } else {
    await ctx.reply("Search failed. Please try again.");
  }
});

bot.command("weekly", async (ctx) => {
  await ctx.reply("Generating weekly review...");
  const response = await fetch(`${process.env.API_URL || "http://localhost:8000"}/api/weekly`);
  if (response.ok) {
    const data = await response.json();
    await ctx.reply(data.content || "No weekly summary available yet.");
  } else {
    await ctx.reply("Unable to fetch weekly summary.");
  }
});

bot.command("stats", async (ctx) => {
  const response = await fetch(`${process.env.API_URL || "http://localhost:8000"}/api/stats`);
  if (response.ok) {
    const stats = await response.json();
    const message = [
      "📊 Your Life Data Lake Statistics:",
      "",
      `💬 Total Messages: ${stats.total_messages}`,
      `🖼️ Media Files: ${stats.total_media}`,
      `🔗 Links Processed: ${stats.total_links}`,
      `📝 Daily Summaries: ${stats.total_summaries}`,
      `📅 Active Days: ${stats.active_days}`,
    ].join("\n");
    await ctx.reply(message);
  } else {
    await ctx.reply("Unable to fetch statistics.");
  }
});

bot.command("idea", async (ctx) => {
  const response = await fetch(`${process.env.API_URL || "http://localhost:8000"}/api/random-idea`);
  if (response.ok) {
    const data = await response.json();
    await ctx.reply(`💡 ${data.text}`);
  } else {
    await ctx.reply("Unable to fetch idea. Make sure you have ideas recorded.");
  }
});

bot.command("help", async (ctx) => {
  const helpText = `
🆘 Help - Life Data Lake Bot Commands

/today - Get today's summary and reflections
/search <query> - Search through your messages
/weekly - Get your weekly review and insights
/stats - View your personal statistics
/idea - Get a random idea from your collection
/help - Show this help message

Your data is stored locally and processed with AI for insights.
  `.trim();
  await ctx.reply(helpText);
});

bot.on("message", async (ctx) => {
  if (ctx.message.text && !ctx.message.text.startsWith("/")) {
    await ctx.reply(
      "I'm a bot interface for Life Data Lake. " +
      "Use /help to see available commands."
    );
  }
});

bot.catch((err) => {
  console.error("Bot error:", err);
});

async function main() {
  console.log("Starting Life Data Lake Bot...");
  await bot.init();
  await bot.start();
  console.log("Bot is running!");
}

main().catch(console.error);