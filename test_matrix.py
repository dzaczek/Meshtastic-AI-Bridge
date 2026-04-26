#!/usr/bin/env python3
"""Quick test: check Matrix bridge rooms, create missing, send test msg."""
import asyncio
import config
from nio import (
    AsyncClient, LoginResponse,
    RoomResolveAliasResponse, RoomCreateResponse,
)

async def main():
    client = AsyncClient(config.MATRIX_HOMESERVER, config.MATRIX_USERNAME)
    resp = await client.login(config.MATRIX_PASSWORD)
    if not isinstance(resp, LoginResponse):
        print(f"Login FAILED: {resp}")
        return
    print(f"Logged in as {resp.user_id}")

    domain = config.MATRIX_HOMESERVER.replace("https://", "").replace("http://", "").split(":")[0].rstrip("/")
    prefix = getattr(config, "MATRIX_ROOM_PREFIX", "mesh")
    invite = getattr(config, "MATRIX_INVITE_USERS", [])
    print(f"Domain: {domain}, Prefix: {prefix}, Invite: {invite}")

    # Ensure ch0 room
    for room_name, display in [("ch0", "Mesh: PRIMARY"), ("dm", "Mesh: Direct Messages")]:
        alias_local = f"{prefix}-{room_name}"
        alias_full = f"#{alias_local}:{domain}"
        r = await client.room_resolve_alias(alias_full)
        if isinstance(r, RoomResolveAliasResponse):
            print(f"  {alias_full} -> EXISTS {r.room_id}")
            # Re-invite
            for u in invite:
                inv = await client.room_invite(r.room_id, u)
                print(f"    Invite {u}: {type(inv).__name__}")
        else:
            print(f"  {alias_full} -> NOT FOUND, creating...")
            cr = await client.room_create(
                name=display,
                alias=alias_local,
                topic=f"Meshtastic bridge: {room_name}",
                invite=invite,
            )
            if isinstance(cr, RoomCreateResponse):
                print(f"    Created: {cr.room_id}")
            else:
                print(f"    FAILED: {cr}")

    # Send test message to ch0
    r0 = await client.room_resolve_alias(f"#{prefix}-ch0:{domain}")
    if isinstance(r0, RoomResolveAliasResponse):
        sr = await client.room_send(
            r0.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "[Bridge Test] connectivity OK"},
        )
        print(f"Test msg to ch0: {type(sr).__name__}")

    jr = await client.joined_rooms()
    rooms = jr.rooms if hasattr(jr, "rooms") else []
    print(f"Joined rooms ({len(rooms)}): {rooms}")

    await client.close()

asyncio.run(main())
