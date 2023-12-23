import os, discord, random, re, asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GENIE = 243236171591712789
RALF = 550523153302945792
AUTHS = [GENIE, RALF] #accounts authorized to use the bot
SCHEDULE_CHANNEL_ID = 1085673812663738388 #id of channel where missions get posted
TESTING_CHANNEL_ID = int(os.getenv('TESTING_CHANNEL'))
CONFIRMATION_MSG = None
INTERPOINT = None
REPLACEMENT_GRACE_PERIOD = 900 #seconds
NUMBER_OF_PILOTS = 4 #idk when this wouldn't be 4 but who knows
MISSION_CHANNELS = {} #key: role, value: channel
PENDING_REPLACEMENTS = {} #key: message, value: [old member, new member, role]
RALF_MSG = '@everyone is now here, please read the pinned post WITH UTMOST CARE'

class PilotPickerClient(discord.Client):
    LAST_USER = None

    async def on_ready(self):
        global AUTHS, MISSION_CHANNELS, locked, timer
        locked = False
        INTERPOINT = self.get_guild(734728132313219183)
        mod_role = INTERPOINT.get_role(787918811784806410)
        for moderator in mod_role.members:
            AUTHS.append(moderator.id)
            print(f'Added {moderator.display_name} to moderator list')

        channel_names = {}
        for channel in INTERPOINT.channels:
            channel_names[channel.name] = channel
        for role in INTERPOINT.roles:
            if ('Open' in role.name and ' Crew' in role.name):
                crew_number = re.findall(r'\d+', role.name)[0]
                if (int(crew_number) < 10):
                    crew_number = '0' + crew_number
                channel = channel_names['open-crew-' + crew_number]    
                MISSION_CHANNELS[role] = channel
                print(f'Added {role.name} to dict')

    async def replacement_timer(self):
        try:
            await asyncio.sleep(REPLACEMENT_GRACE_PERIOD)
        except asyncio.CancelledError:
            print('Timer skipped')

    async def on_message(self, message):
        global CONFIRMATION_MSG, AUTHS, locked, timer
        if (message.author == self.user):
            return
        channel = message.channel
        if (channel.type == discord.ChannelType.private and message.author.id in AUTHS):
            if (not locked):
                sent_message = await channel.send('Click to roll open missions')
                await sent_message.add_reaction('✅')
                CONFIRMATION_MSG = sent_message
            else:
                await channel.send('Bot currently in use, try again later')
        elif (channel.type == discord.ChannelType.public_thread and message.author.id != RALF):
            if (channel.parent.id == SCHEDULE_CHANNEL_ID and message.mentions):
                print(f'Initiating replacement of {message.mentions[0].display_name}')
                dupes = []
                while (True):
                    failed, sent_message, dupes = await self.roll_replacement(message, dupes)
                    if (failed):
                        await message.add_reaction('❌')
                        break
                    timer = asyncio.create_task(self.replacement_timer())
                    await timer
                    if (sent_message in PENDING_REPLACEMENTS.keys()):
                        await sent_message.clear_reactions()
                        await channel.send('Rerolling...', delete_after=5)
                        del PENDING_REPLACEMENTS[sent_message]
                    else:
                        break

    async def on_reaction_add(self, reaction, user):
        global CONFIRMATION_MSG, LAST_USER, locked, timer
        if (user == self.user):
            return
        if (reaction.message == CONFIRMATION_MSG):
            locked = True
            LAST_USER = user
            await self.roll_pilots()
            CONFIRMATION_MSG = None
        if (reaction.message in PENDING_REPLACEMENTS.keys()):
            replacement_data = PENDING_REPLACEMENTS[reaction.message]
            if(user == replacement_data[1]):
                if(reaction.emoji == '✅'):
                    await self.resolve_replacement(replacement_data)
                    del PENDING_REPLACEMENTS[reaction.message]
                    await reaction.message.clear_reactions()
                    await reaction.message.channel.send('Success!')
                elif(reaction.emoji == '⏭️'):
                    timer.cancel()

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
        for mission in rollable_missions:
            output = ''
            crew_role = (set(mission.role_mentions).intersection(MISSION_CHANNELS.keys())).pop()
            print(f'Crew role is {crew_role}')
            gm = (mission.mentions)[0]
            await gm.add_roles(crew_role)
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
                member = random.choice(pilots)
                if (not member or member.id == RALF):
                    pilots.remove(member)
                    continue
                if (member not in dupes or dupes_needed):
                    output += (f'<@{member.id}> ')
                    dupes.append(member)
                    pilots.remove(member)
                    try:
                        await member.add_roles(crew_role)
                        print(f'Added {crew_role.name} role to {member.display_name}')
                    except: 
                        await LAST_USER.send(f'Failed to add {crew_role} to {member.display_name}')
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
            try:
                await mission_channel.send(RALF_MSG)
            except:
                await LAST_USER.send(f'Failed to send message in {mission_channel.name}')
        await LAST_USER.send('All done!')
        dupes.clear()
        locked = False

    async def roll_replacement(self, message, dupes):
        pilot_to_replace = message.mentions[0]
        thread = message.channel
        mission = await thread.parent.fetch_message(thread.id)
        crew_role = (set(mission.role_mentions).intersection(MISSION_CHANNELS.keys())).pop()
        print(f'Crew role is {crew_role.name}')
        if (crew_role not in pilot_to_replace.roles):
            print(f'Failed to roll replacement: invalid user')
            await thread.send('Failed to roll replacement: invalid user')
            return True, None, None
        applications = (mission.reactions)[0]
        pilots = [user async for user in applications.users()]
        while (True):
            if (not pilots):
                    print(f'Ran out of pilots to replace for {crew_role.name}')
                    await thread.send(f'Ran out of pilots to replace for {crew_role.name}')
                    return True, None, None
            member = random.choice(pilots)
            if (not member or member.id == RALF or crew_role in member.roles or member in dupes):
                    pilots.remove(member)
                    continue
            print(f'{member.display_name} chosen')
            replacement = member
            dupes.append(member)
            break
        sent_message = await thread.send(f'Replacing {pilot_to_replace.display_name}, <@{replacement.id}> has been rolled as a substitute. You have 15 minutes to accept or pass.')
        await sent_message.add_reaction('✅')
        await sent_message.add_reaction('⏭️')
        PENDING_REPLACEMENTS[sent_message] = [pilot_to_replace, replacement, crew_role]
        return False, sent_message, dupes
    
    async def resolve_replacement(self, replacement_data):
        pilot_to_replace = replacement_data[0]
        replacement = replacement_data[1]
        crew_role = replacement_data[2]
        #remove role from old player
        try:
            await pilot_to_replace.remove_roles(crew_role)
            print(f'Removed {crew_role.name} role from {pilot_to_replace.display_name}')
        except: 
            await LAST_USER.send(f'Failed to remove {crew_role} from {pilot_to_replace.display_name}')
        #give role to replacement
        try:
            await replacement.add_roles(crew_role)
            print(f'Added {crew_role.name} role to {replacement.display_name}')
        except:
            await LAST_USER.send(f'Failed to add {crew_role} to {replacement.display_name}')
        print(f'Finished replacement for {crew_role}')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = PilotPickerClient(intents=intents)
client.run(TOKEN)