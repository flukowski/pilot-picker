import os, discord, random, re, asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LINK_PREFIX = 'https://discord.com/channels/734728132313219183/1105416342368169985/'
GENIE = 243236171591712789
RALF = 550523153302945792
AUTHS = [RALF] # accounts authorized to use the bot
OPEN_MISSION_CHANNEL_ID = 1085673812663738388 # id of channel where open missions get posted
WILD_WEST_CHANNEL_ID = 1105416342368169985
try:
    TESTING_CHANNEL_ID = int(os.getenv('TESTING_CHANNEL'))
except Exception:
    print("No testing channel enviornment variable found (this is fine)")
INTERPOINT = None
REPLACEMENT_GRACE_PERIOD = 900 # seconds
NUMBER_OF_PILOTS = 4 # idk when this wouldn't be 4 but who knows
OPEN_MISSION_CHANNELS = {} # key: role, value: channel
WILD_WEST_CHANNELS = {} # key: role, value: channel
PENDING_REPLACEMENTS = {} # key: message, value: [old member, new member, role, timer]
RALF_MSG = '@everyone is now here, please read the pinned post WITH UTMOST CARE'
HELP_MSG = '''```
?help - shows list of commands \n
?roll_ww (link to mission post) (optional: number of pilots to roll if not 4) - rolls pilots for the linked wild west game \n
?roll_open - rolls all new open missions \n
(ping a player in an open mission or wild west thread) - replace that player, substitutes randomly chosen every 15 minutes```'''

class PilotPickerClient(discord.Client):
    last_user = None

    async def on_ready(self):
        global locked, INTERPOINT
        locked = False
        INTERPOINT = self.get_guild(734728132313219183)
        mod_role = INTERPOINT.get_role(787918811784806410)
        caretaker_role = INTERPOINT.get_role(1216005988738666536)

        for user in set(mod_role.members).union(set(caretaker_role.members)):
            AUTHS.append(user.id)
            print(f'Added {user.display_name} to user list')

        channel_names = {}
        for channel in INTERPOINT.channels:
            channel_names[channel.name] = channel

        for role in INTERPOINT.roles:

            if ('Open' in role.name and ' Crew' in role.name):
                try:
                    crew_number = re.findall(r'\d+', role.name)[0]
                    if (int(crew_number) < 10):
                        crew_number = '0' + crew_number
                    channel = channel_names['open-crew-' + crew_number]    
                    OPEN_MISSION_CHANNELS[role] = channel
                    print(f'Added {role.name} to open mission dict')
                except(Exception):
                    continue

            elif ('CowboyCrew' in role.name):
                crew_number = re.findall(r'\d+', role.name)[0]
                channel = channel_names['cowboy-crew-' + crew_number]    
                WILD_WEST_CHANNELS[role] = channel
                print(f'Added {role.name} to wild west dict')

    async def replacement_timer(self):
        try:
            await asyncio.sleep(REPLACEMENT_GRACE_PERIOD)
        except asyncio.CancelledError:
            print('Timer skipped')

    async def on_message(self, message: discord.Message):
        global LAST_USER, locked
        if (message.author == self.user):
            return
        
        channel = message.channel
        if (channel.type == discord.ChannelType.private and message.author.id in AUTHS):
            print(f'{message.author}: {message.content}')

            if (message.content.startswith('?help')):
                await message.channel.send(HELP_MSG)

            elif (message.content.startswith('?roll_ww')):
                await self.roll_wild_west(message)

            elif (message.content.startswith('?roll_open')):
                if (not locked):
                    locked = True
                    LAST_USER = message.author
                    await self.roll_open_missions()
                else:
                    await channel.send('Already rolling open missions, try again later')

        elif (channel.type == discord.ChannelType.public_thread and message.mentions and message.author.id in AUTHS):
            if (channel.parent.id == OPEN_MISSION_CHANNEL_ID or channel.parent.id == WILD_WEST_CHANNEL_ID):
                print(f'Initiating replacement of {message.mentions[0].display_name}')

                dupes = []
                while (True):
                    failed, sent_message, dupes = await self.roll_replacement(message, dupes)
                    if (failed):
                        await message.add_reaction('❌')
                        break

                    PENDING_REPLACEMENTS[sent_message].append(asyncio.create_task(self.replacement_timer()))
                    await PENDING_REPLACEMENTS[sent_message][3] # start the timer

                    if (sent_message in PENDING_REPLACEMENTS.keys()):
                        await sent_message.clear_reactions()
                        await channel.send('Rerolling...', delete_after=5)
                        del PENDING_REPLACEMENTS[sent_message]
                    else:
                        break

    async def on_reaction_add(self, reaction, user):
        global LAST_USER
        if (user == self.user):
            return
        
        if (reaction.message in PENDING_REPLACEMENTS.keys()):
            replacement_data = PENDING_REPLACEMENTS[reaction.message]

            if(user == replacement_data[1]):
                if(reaction.emoji == '✅'):
                    await self.resolve_replacement(replacement_data)
                    del PENDING_REPLACEMENTS[reaction.message]
                    await reaction.message.clear_reactions()
                    await reaction.message.channel.send('Success!')

                elif(reaction.emoji == '⏭️'):
                    PENDING_REPLACEMENTS[reaction.message][3].cancel()

    async def roll_open_missions(self):
        global locked
        schedule = self.get_channel(OPEN_MISSION_CHANNEL_ID)
        rollable_missions = []
        await LAST_USER.send('Rolling pilots...')

        async for mission_post in schedule.history(limit=100):
            if (not mission_post.flags.has_thread):
                rollable_missions.append(mission_post)
                print(f'Added {mission_post.id} to mission list')
                
        dupes = []
        for mission in rollable_missions:
            try:
                crew_role = (set(mission.role_mentions).intersection(OPEN_MISSION_CHANNELS.keys())).pop()
            except:
                print(f'failed to roll {mission.id}: missing crew role')
                continue
            print(f'Crew role is {crew_role}')

            gm = (mission.mentions)[0]
            await gm.add_roles(crew_role)
            print(f'Added {crew_role.name} role to {gm.display_name}')
            output = (f'GM: <@{gm.id}>\nPlayers: ')

            applications = (mission.reactions)[0]
            pilots = [user async for user in applications.users()]
            pilot_count = 0
            dupes_needed = False

            while (pilot_count < NUMBER_OF_PILOTS):
                if (not pilots):
                    print(f'Ran out of pilots for {crew_role}')
                    break

                member = random.choice(pilots)
                member = INTERPOINT.get_member(member.id)

                if (not member or member.id == RALF or member == gm):
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

            print(f'Mission {crew_role} complete')
            thread = await mission.create_thread(name = 'Applications Closed')
            await thread.send(output)

            async for threadmsg in schedule.history(limit=1):
                if (threadmsg.type == discord.MessageType.thread_created):
                    await threadmsg.delete()

            mission_channel = OPEN_MISSION_CHANNELS[crew_role]
            try:
                await mission_channel.send(RALF_MSG)
            except:
                print(f'Failed to send message in {mission_channel.name}')

        await LAST_USER.send('All done!')
        locked = False
    
    async def roll_wild_west(self, message):
        schedule = self.get_channel(WILD_WEST_CHANNEL_ID)
        number_of_pilots = NUMBER_OF_PILOTS
        link_index = message.content.find(LINK_PREFIX)

        if (link_index == -1):
            await message.channel.send('Couldn\'t find that game, sorry!')
            return
        
        arguments = message.content[link_index + len(LINK_PREFIX):].split(' ')
        mission = await schedule.fetch_message(arguments[0])

        if (mission.flags.has_thread):
            await message.channel.send('Looks like that mission already got rolled ¯\_(ツ)_/¯')
            print('stopped: already rolled')
            return
        
        if (len(arguments)>1):
            number_of_pilots = re.findall(r'\d+', arguments[1])[0]
        print(f'mission roster size: {number_of_pilots}')

        try:
            crew_role = (set(mission.role_mentions).intersection(WILD_WEST_CHANNELS.keys())).pop()
        except:
            await message.channel.send('Missing crew role')
            print('stopped: missing crew role')
            return
        print(f'Crew role is {crew_role}')

        gm = (mission.mentions)[0]
        await gm.add_roles(crew_role)
        print(f'Added {crew_role.name} role to {gm.display_name}')
        output = (f'GM: <@{gm.id}>\nPlayers: ')

        applications = (mission.reactions)[0]
        pilots = [user async for user in applications.users()]
        pilot_count = 0

        while (pilot_count < number_of_pilots):
            if (not pilots):
                print(f'Ran out of pilots for {crew_role}')
                break

            member = random.choice(pilots)

            if (not member or member.id == mission.author.id):
                pilots.remove(member)
                continue
            output += (f'<@{member.id}> ')
            pilots.remove(member)

            try:
                await member.add_roles(crew_role)
                print(f'Added {crew_role.name} role to {member.display_name}')
            except:
                print(f'Failed to add {crew_role} to {member.display_name}')

            pilot_count += 1
            continue

        thread = await mission.create_thread(name = 'Applications Closed')
        await thread.send(output)
        async for threadmsg in schedule.history(limit=1):
            if (threadmsg.type == discord.MessageType.thread_created):
                await threadmsg.delete()
        await message.channel.send('All done!')

    async def roll_replacement(self, message, dupes):
        pilot_to_replace = message.mentions[0]
        
        thread = message.channel
        mission = await thread.parent.fetch_message(thread.id)

        if (thread.parent.id == WILD_WEST_CHANNEL_ID):
            crew_role = (set(mission.role_mentions).intersection(WILD_WEST_CHANNELS.keys())).pop()
        else:
            crew_role = (set(mission.role_mentions).intersection(OPEN_MISSION_CHANNELS.keys())).pop()
        print(f'Crew role is {crew_role.name}')

        if crew_role not in pilot_to_replace.roles:
            return True, None, None
        
        applications = (mission.reactions)[0]
        pilots = [user async for user in applications.users()]

        while (True):
            if (not pilots):
                    print(f'Ran out of pilots to replace for {crew_role.name}')
                    await thread.send(f'Ran out of pilots to replace for {crew_role.name}')
                    return True, None, None
            
            member = random.choice(pilots)
            member = INTERPOINT.get_member(member.id)

            if (not member):
                pilots.remove(member)
                continue

            if (member.id == RALF or member.id == pilot_to_replace.id or crew_role in member.roles or member in dupes):
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

        try:
            await pilot_to_replace.remove_roles(crew_role)
            print(f'Removed {crew_role.name} role from {pilot_to_replace.display_name}')
        except: 
            print(f'Failed to remove {crew_role} from {pilot_to_replace.display_name}')

        try:
            await replacement.add_roles(crew_role)
            print(f'Added {crew_role.name} role to {replacement.display_name}')
        except:
            print(f'Failed to add {crew_role} to {replacement.display_name}')
        print(f'Finished replacement for {crew_role}')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = PilotPickerClient(intents=intents)
client.run(TOKEN)