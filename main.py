import discord
import argparse

from market_item import MarketItem
from memeuser import MemeUser

parser = argparse.ArgumentParser(description='Discord bot to facilitate investing in posts.')
# required arguments
parser.add_argument('-t', '--token', help='your discord bot token', required=True)
parser.add_argument('-c', '--channel', help='the channel ID designated for investing', required=True)
# optional arguments
parser.add_argument('--init_balance', help='the balance that users start at initially', required=False, default=200)
parser.add_argument('--init_post', help='the balance that posts start at. Higher makes returns lower', required=False, default=1000)
parser.add_argument('-d', '--dev', help='enables some developer commands', required=False, default=False, action='store_true')

args = parser.parse_args()

TOKEN = args.token
channelID = int(args.channel)

client = discord.Client()

# global values
userlist = []
initbalance = int(args.init_balance)
init_post_balance = int(args.init_post)
activeMarkets = []
memechannel = None
skim_percent = 0.02


# TRIGGERED FUNCTIONS
@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------------')

    # Load some required information and cache in memory
    global memechannel
    global userlist
    memechannel = client.get_channel(channelID)
    if memechannel is not None:
        print("Meme channel detected")
    else:
        print("Channel not detected")
        exit(420)
    potentialUsers = memechannel.guild.members
    for m in potentialUsers:
        if m != client.user and await meme_user_exists(m.id) is False:
            nu = MemeUser(m.id, initbalance)
            userlist.append(nu)
    print("{} users detected and processed".format(len(userlist)))
    print("User starting balance: ${}".format(initbalance))
    if args.dev is True:
        print("Starting Bot in DEVELOPER MODE")
    print("------------")

@client.event
async def on_member_join(member):
    if await meme_user_exists(member.id) is False:
        nu = MemeUser(member.id, initbalance)
        userlist.append(nu)
        print("New User added and given ${} in starting money".format(initbalance))


@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return

    # If the message is a DM it will check these conditions
    if message.guild is None:
        print(message.content)

        if message.content.lower().startswith('!help'):             # show the user the available commands
            await get_help(message)
        elif message.content.lower().startswith('!balance'):        # show the user only their current balance
            await check_balance(message)
        elif message.content.lower().startswith('!portfolio'):      # show the user what investments they have
            await show_investments(message)
        elif message.content.lower().startswith('!val'):
            await change_default_investment(message)
        elif message.content.lower().startswith('!sell'):
            await sell(message)
        elif message.content.lower().startswith('!my_id'):
            await message.channel.send(message.author.id)
        elif message.content.lower().startswith("!bankrupt"):
            await declare_bankruptcy(message)
        elif message.content.lower().startswith("!subtract"):
            await subtract(message)
        elif message.content.lower().startswith("!add"):
            await add(message)
        elif message.content.lower().startswith("!shutdown"):
            await shutdown()

    else:  # The message is NOT a DM it will count it for investing if it is in the correct channel
        # We add the up and downvote reactions and add the post to a list for counting
        if message.channel.id == channelID:
            await message.add_reaction('👍')
            await message.add_reaction('👎')

            mi = MarketItem(init_post_balance, message)
            activeMarkets.append(mi)


# This function is called when a reaction is added to a message
# Only applies to messages sent AFTER the bot joined the server
@client.event
async def on_reaction_add(reaction, user):
    # Ignore reactions in other channels and reactions made by the bot
    if reaction.message.channel.id != channelID or user == client.user:
        return

    if reaction.emoji == '👍':
        await create_investment(reaction.message, user)
    elif reaction.emoji == '👎':
        mi = await get_market_item(reaction.message.id)
        mi.downvote()


@client.event
async def on_reaction_remove(reaction, user):
    if reaction.emoji == '👎':
        mi = await get_market_item(reaction.message.id)
        mi.remove_downvote()


# DEVELOPER &/OR ADMIN FUNCTIONS
async def subtract(message):
    """
    Developer function to subtract funds
    """
    if args.dev is True:
        user = await get_user(message.author.id)
        m = message.content.split(' ')
        user.balance -= int(m[1])
        await message.channel.send("Your new balance is `${}`".format(user.balance))


async def add(message):
    """
    Developer function to add funds
    """
    if args.dev is True:
        user = await get_user(message.author.id)
        m = message.content.split(' ')
        user.balance += int(m[1])
        await message.channel.send("Your new balance is `${}`".format(user.balance))


async def shutdown():
    if args.dev is True:
        # TODO save log information or something
        print("SHUTDOWN COMMAND RECEIVED, SHUTTING DOWN")
        exit(0)


# USER FUNCTIONS
async def get_help(message):
    msg = 'Hello {0.author.mention}, here are some things you can ask me: \n' \
          '\t`!help` - Displays this help dialog.\n' \
          '\t`!balance` - Get information about your current balance.\n' \
          '\t`!portfolio` - Get information about your current investment portfolio.\n' \
          '\t`!val %INTEGER%` - Change your default investment value for new investments.\n' \
          '\t`!sell %INVESTMENT ID%` - Sell your investment for its current value.\n' \
          '\t`!sell all` - Sell all outstanding investments for their current value.\n' \
          '\t`!bankrupt` - Usable only when close to $0 to help you get back on your feet. Don\'t just say it, declare it. \n' \
          '**Instructions:**\n' \
          'To invest in memes simply react to them with 👍\n' \
          'When investing with 👍, you will always invest what your `default_investment` is set to.'.format(message)
    await message.channel.send(msg)


async def change_default_investment(message):
    m = message.content.split(' ')
    if len(m) != 2:
        await message.channel.send("Please ensure there is only a single number argument after the command.")
        return None
    try:
        new_val = int(m[1])
    except ValueError:
        await message.channel.send("Sorry, that wasn't a number.")
        return None
    user = await get_user(message.author.id)
    user.default_invest = new_val
    await message.channel.send("Default Investment Value changed to `${}`".format(new_val))


async def check_balance(message):
    userID = message.author.id
    for u in userlist:
        if u.ID == userID:
            msg = "Here is your balance information:\n" \
                  "`Balance: ${}`\n" \
                  "`Total Investments Outstanding: ${}`\n" \
                  "`Default investment amount: ${}`".format(u.balance, u.get_outstanding(), u.default_invest)
            await message.channel.send(msg)
            return


async def create_investment(message, discord_user):
    mi = await get_market_item(message.id)
    meme_user = await get_user(discord_user.id)
    if meme_user is None:
        print("User does not exist")
        print("this should probably not happen?")
        return
    else:
        ret = meme_user.add_investment(message.id, mi.value, mi)
        # ret is returned None if the investment is not added
        if ret is None:
            print("Investment not added, user insufficient funds")
            return None
        else:
            if message.author.id != discord_user.id:
                # the user who posted the meme gets a kickback for posting a dank meme
                meme_poster = await get_user(message.author.id)
                meme_poster.balance += int(meme_user.default_invest * skim_percent)

            # if the user has not messaged the bot since it has started it first needs to create the DM channel
            if discord_user.dm_channel is None:
                await discord_user.create_dm()

            # Then send the confirmation DM
            await discord_user.dm_channel.send("You have successfully invested ${}".format(meme_user.default_invest))


async def show_investments(message):
    uid = message.author.id
    user = await get_user(uid)
    msg = user.get_investment_display()
    if msg is not None:
        await message.channel.send(msg)
    else:
        await message.channel.send("You currently have `0` investments.")
    await message.channel.send("You have declared bankruptcy {} times.".format(user.bankrupt_count))


async def sell(message):
    m = message.content.split(' ')
    user = await get_user(message.author.id)

    if len(m) != 2:
        await message.channel.send("Please ensure there is only a single number argument after the command.")
        return None
    elif m[1] == 'all':
        income = user.sell_all()
    else:
        income = user.sell(int(m[1]))

    if income is None:
        await message.channel.send("You do not have any investments with that ID.")
    else:
        await message.channel.send("Income from sale: `${}`".format(income))


async def declare_bankruptcy(message):
    user = await get_user(message.author.id)
    # if the user has no outstanding investments and has less then a quarter of the starting value
    if user.get_outstanding() == 0 and user.balance < initbalance / 4:
        user.bankrupt(initbalance / 4)
        await message.channel.send("You have successfully declared bankruptcy. You have been granted "
                                   "an initial balance of ${}.".format(initbalance / 4))
    elif user.get_outstanding() != 0:
        await message.channel.send("You cannot declare bankruptcy unless you have 0 investments.")
    else:
        await message.channel.send("You have too much money to declare bankruptcy.")


# UTILITY FUNCTIONS
async def meme_user_exists(checkID):
    for u in userlist:
        if u.ID == checkID:
            return True
    return False


# TODO order userlist and use a better search method like quicksearch im just lazy. fine for small servers
async def get_user(uid):
    for u in userlist:
        if u.ID == uid:
            return u
    return None  # this shouldn't happen


async def get_market_item(mid):
    for m in activeMarkets:
        if m.id == mid:
            return m
    return None


client.run(TOKEN)