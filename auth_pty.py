#!/usr/bin/env python3
import asyncio
import sys
from telethon import TelegramClient

async def auth():
    print("Starting Telegram authentication...")
    print("Check your Telegram app for the verification code.")
    
    client = TelegramClient('life-data-lake', 38181387, 'ce5bfd0f81ba17025de0856aebd6e157')
    
    try:
        await client.start(phone='+919739241080')
        me = await client.get_me()
        print(f"SUCCESS: Logged in as {me.first_name} ({me.id})")
        
        # Verify chat access
        try:
            entity = await client.get_entity(-1003916280400)
            print(f"SUCCESS: LifeOS chat found: {entity.title}")
        except Exception as e:
            print(f"Chat access: {e}")
        
        await client.disconnect()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(auth())
