#!/usr/bin/env python3
"""Helper script to complete Telegram authentication."""

import sys
import asyncio
from telethon import TelegramClient

async def complete_auth():
    if len(sys.argv) < 2:
        print("Usage: python auth_helper.py <auth_code>")
        print("Check your Telegram for the auth code.")
        return
    
    code = sys.argv[1]
    
    client = TelegramClient('life-data-lake', 38181387, 'ce5bfd0f81ba17025de0856aebd6e157')
    
    await client.start(phone='+919739241080')
    
    # If 2FA is enabled, you may need password too
    # For now just complete with code
    
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} ({me.id})")
    
    # Try to access the LifeOS chat
    try:
        entity = await client.get_entity(-1003916280400)
        print(f"LifeOS chat found: {entity.title}")
    except Exception as e:
        print(f"Chat access: {e}")
    
    await client.disconnect()
    print("Authentication successful!")

if __name__ == "__main__":
    asyncio.run(complete_auth())
