import os, discord, random
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
RALF = 550523153302945792
AUTHS = [243236171591712789, RALF] #accounts authorized to roll
SCHEDULE_CHANNEL_ID = 1085673812663738388 #id of channel where missions get posted
CONFIRMATION_ID = None
NUMBER_OF_PILOTS = 4 #idk when this wouldn't be 4 but who knows
MISSION_CHANNELS = {}
RALF_MSG = '@everyone is now here, please read the pinned post WITH UTMOST CARE'

class PilotPickerClient(discord.Client):
    LAST_USER = None

    async def on_ready(self):
        global AUTHS, MISSION_CHANNELS, locked
        locked = False
        interpoint = self.get_guild(734728132313219183)
        mod_role = interpoint.get_role(787918811784806410)
        for moderator in mod_role.members:
            AUTHS.append(moderator.id)
            print(f'Added {moderator.display_name} to moderator list')

        channel_names = {}
        for channel in interpoint.channels:
            channel_names[channel.name] = channel
        for role in interpoint.roles:
            if ('Open' in role.name and ' Crew' in role.name):
                crew_number = re.findall(r'\d+', role.name)[0]
                if (int(crew_number) < 10):
                    crew_number = '0' + crew_number
                channel = channel_names['open-crew-' + crew_number]    
                MISSION_CHANNELS[role] = channel
                print(f'Added "key: {role.name} value: {channel.name}" to dict')

    async def on_message(self, message):
        global CONFIRMATION_ID, AUTHS, locked
        channel = message.channel
        if (channel.type == discord.ChannelType.private and message.author.id in AUTHS):
            if (not locked):
                sent_message = await channel.send('Click to confirm')
                await sent_message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
                CONFIRMATION_ID = sent_message.id
            else:
                await channel.send('Bot currently in use, try again later')

    async def on_reaction_add(self, reaction, user):
        global CONFIRMATION_ID, LAST_USER, locked
        if (user == self.user):
            return
        if (reaction.message.id == CONFIRMATION_ID):
            locked = True
            LAST_USER = user
            await self.roll_pilots()

    async def roll_pilots(self):
        global SCHEDULE_CHANNEL_ID, NUMBER_OF_PILOTS, LAST_USER, locked
        schedule = self.get_channel(SCHEDULE_CHANNEL_ID)
        rollable_missions = []
        await LAST_USER.send('Rolling pilots...')
        async for mission_post in schedule.history(limit=30):
            if (not mission_post.flags.has_thread): 
                rollable_missions.append(mission_post)
                print(f'Added {mission_post.id} to mission list')
        dupes = []
        interpoint = schedule.guild
        for mission in rollable_missions:
            output = ''
            crew_role = (set(mission.role_mentions).intersection(MISSION_CHANNELS.keys())).pop()
            print(f'Crew role is {crew_role}')
            gm = (mission.mentions)[0]
            await interpoint.get_member(gm.id).add_roles(crew_role)
            print(f'Added {crew_role.name} role to {gm.display_name}')
            output += (f'GM: <@{gm.id}>\nPlayers: ')
            applications = (mission.reactions)[0]
            pilots = [user async for user in applications.users()]
            pilot_count = 0
            dupes_needed = False
            while (pilot_count < NUMBER_OF_PILOTS):
                if (not pilots):
                    print(f'Ran out of pilots for {crew_role}')
                    break
                member = interpoint.get_member(random.choice(pilots).id)
                if (not member or member.id == RALF):
                    pilots.remove(member)
                    continue
                if (member not in dupes or dupes_needed):
                    output += (f'<@{member.id}> ')
                    dupes.append(member)
                    pilots.remove(member)
                    await interpoint.get_member(member.id).add_roles(crew_role)
                    print(f'Added {crew_role.name} role to {member.display_name}')
                    pilot_count += 1
                    continue
                if (set(pilots).issubset(dupes)):
                    print('Allowing duplicates')
                    dupes_needed = True
            await LAST_USER.send(output)
            await LAST_USER.send(f'Mission {crew_role} complete')
            thread = await mission.create_thread(name = 'Applications Closed')
            await thread.send(output)
            async for threadmsg in schedule.history(limit=1):
                if (threadmsg.type == discord.MessageType.thread_created):
                    await threadmsg.delete()
            mission_channel = MISSION_CHANNELS[crew_role]
            await mission_channel.send(RALF_MSG)
        await LAST_USER.send('All done!')
        dupes.clear()
        locked = False

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = PilotPickerClient(intents=intents)
client.run(TOKEN)