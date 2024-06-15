import asyncio
from asyncio import sleep
from contextlib import suppress
from datetime import datetime, timezone
from os import getenv
from random import randbytes, randint

from asyncpg import Connection, create_pool
from asyncpg.pool import PoolAcquireContext
from dotenv import load_dotenv
from telethon import TelegramClient, events, types
from telethon.functions import account
from telethon.tl.custom import Dialog

load_dotenv()


class DBContext:
    def __init__(self, con: PoolAcquireContext) -> None:
        self._con = con

    async def __aenter__(self) -> Connection:
        return await self._con.__aenter__()

    async def __aexit__(self, *args):
        await self._con.__aexit__(*args)


class DataBase:
    def __init__(self, **connect_kwargs) -> None:
        self.connect_kwargs = connect_kwargs

    def get_connection(self):
        return DBContext(self._pool.acquire())

    async def __aenter__(self):
        self._pool = await create_pool(**self.connect_kwargs).__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._pool.__aexit__(*args)


async def set_online(client: TelegramClient):
    retries = 3
    while not await client(account.UpdateStatusRequest(False)) and retries > 0:
        await sleep(5)
        retries -= 1
    if retries == 0:
        print("Can't be online")


class UserUpdateHandler:
    def __init__(
        self, client: TelegramClient,
        db: DataBase, user_ids: dict[int, types.User],
        bg_delay: int = 120, bg_simulation_delay: int = 1200,
        bg_simulation_deviation: int = 420
    ) -> None:
        self.client = client
        self.db = db
        self.user_ids = user_ids
        self.bg_delay = bg_delay
        self.simulation_delay = bg_simulation_delay
        self.simulation_deviation = bg_simulation_deviation
        self.simulation_delete_delay_range = (-10, 10)
        self.simulation_entity = await client.get_input_entity(
            getenv("SIMULATION_ENTITY")
        )

        self.online_until: dict[int, datetime] = {}

    async def __call__(self, event: events.UserUpdate.Event):
        # check me going offline
        if event.user_id == (
            await event.client.get_me(True)
        ).user_id and event.online is False:
            await set_online(event.client)

        if event.user_id not in self.user_ids:
            return

        entity = self.user_ids[event.user_id]
        action = f"other: {event.action.__class__.__name__}"
        if event.online is not None:
            if event.online:
                action = "online"
                self.online_until[entity.id] = event.until
            else:
                action = "offline"
                if entity.id in self.online_until:
                    self.online_until.pop(entity.id)
        elif event.recording:
            action = "recording"
        elif event.typing:
            action = "typing"

        async with self.db.get_connection() as con:
            await con.execute(
                "INSERT INTO stats VALUES ($1, $2, $3, $4, $5, $6, $7)",
                entity.id, event.chat_id, entity.username, entity.first_name,
                entity.last_name, datetime.now(timezone.utc), action
            )

    async def bg_online_manager(self):
        while True:
            for tgid, until in self.online_until.items():
                if until <= datetime(tzinfo=timezone.utc):
                    entity = self.user_ids[tgid]
                    async with self.db.get_connection() as con:
                        await con.execute(
                            "INSERT INTO stats VALUES ($1, $2, $3, $4, $5, $6, $7)",
                            entity.id, entity.id, entity.username, entity.first_name,
                            entity.last_name, until, "offline"
                        )
                    self.online_until.pop(tgid)

            await sleep(self.bg_delay)
    
    async def bg_simulation(self):
        while True:
            message = await self.client.send_message(
                self.simulation_entity,
                randbytes(8).hex().upper()
            )

            await sleep(randint(*self.simulation_delete_delay_range))

            await self.client.delete_messages(
                self.simulation_entity, message.id
            )

            await sleep(self.simulation_delay + randint(
                -self.simulation_deviation,
                self.simulation_deviation
            ))
    
    async def __aenter__(self):
        self.bg_tasks = asyncio.gather(
            self.bg_online_manager(),
            self.bg_simulation()
        )

        return self

    async def __aexit__(self, *_):
        self.bg_tasks.cancel()
        await self.bg_tasks


async def main():
    async with DataBase(
        host=getenv("DB_HOST"),
        port=getenv("DB_PORT"),
        user=getenv("DB_USER"),
        password=getenv("DB_PASSWORD"),
        database=getenv("DB_NAME")
    ) as db:
        async with db.get_connection() as con:
            await con.execute(
                """CREATE TABLE IF NOT EXISTS stats (
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    username VARCHAR(32),
                    first_name VARCHAR(64),
                    last_name VARCHAR(64),
                    datetime TIMESTAMP WITH TIME ZONE,
                    action TEXT NOT NULL
                )"""
            )

        async with TelegramClient("account", getenv("API_ID"), getenv("API_HASH")) as client:
            client: TelegramClient

            user_ids = {}
            async for dialog in client.iter_dialogs():
                dialog: Dialog
                if dialog.is_user and dialog.id != (await client.get_me(True)).user_id:
                    user_ids[dialog.id] = dialog.entity
            
            await set_online(client)

            async with UserUpdateHandler(client, db, user_ids) as user_update_handler:
                client.add_event_handler(user_update_handler, events.UserUpdate)

                await client.run_until_disconnected()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
