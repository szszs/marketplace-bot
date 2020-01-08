from MarketAPI import MarketAPI
import multiprocessing
import threading
import time
import json


class ItemSnipe(object):
	"""
	A class used to represent a worker responsible for sniping
	a single item.

	...

	Attributes
	----------
	botClient : MarketAPI.MarketAPI
		the MarketAPI instance used to interface with the marketplace API
	cookie : str
		the cookie of the account used to make purchases
	item_id : str
		the ID of the item the bot is sniping
	item_name : str
		the name of the item the bot is sniping
	item_product_id : str
		the product ID of the item the bot is sniping
	max_price : int
		the maximum price to purchase the item for
	min_price : int
		the minimum price to purchase the item for
	discord_webhook : str
		the webhook of the discord bot that will log messages
	checks : int
		number of times the bot checked the price of the item since the
		last log message (used as a performance metric)
	sniped : int
		number of items the bot has purchased since the last log message
		(used as a performance metric)
	last_update : float
		the last time, in seconds, since a log message was recorded
	log_interval : float
			the interval between log messages, in seconds

	Methods
	-------
	checkAndSnipe()
		Checks the price of the item and purchases it if the price is right.
	restartSession()
		Restarts the session used by the bot.
	run()
		Starts running the bot.
	sendToDiscord(message)
		Logs a message and sends it to Discord.
	"""


	def __init__(self, cookie, item_id, max_price, min_price, discord_webhook, log_interval):
		"""Creates a new ItemSnipe instance.

		Parameters
		----------
		cookie : str
			the cookie of the account used to make purchases
		item_id : str
			the ID of the item the bot is sniping
		max_price : int
			the maximum price to purchase the item for
		min_price : int
			the minimum price to purchase the item for
		discord_webhook : str
			the webhook of the discord bot that will log messages
		log_interval : float
			the interval between log messages, in seconds
		"""

		self.botClient = MarketAPI()
		self.botClient.startSessionNoLogin()

		self.cookie = cookie
		self.botClient.changeCookie(cookie)

		self.discord_webhook = discord_webhook

		self.item_id = item_id
		self.item_name = self.botClient.getAssetNameFromId(self.item_id)
		self.item_product_id = self.botClient.getProductId(self.item_id)
		self.max_price = max_price
		self.min_price = min_price

		self.log_interval = log_interval


	def checkAndSnipe(self):
		"""Checks the price of the item and purchases it if the price is right.

		The bot will purchase the item if the current price is between
		min_price and max_price, inclusive.

		Returns
		----------
		str
			a status message
		str
			a status code. One of three status codes may be returned:
				"ERROR" : 		unexpected behavior, restart the session
				"PURCHASED" : 	purchased the item
				"WAIT" : 		current price is too low or too high
		"""

		# get best price info
		success, info = self.botClient.getMarketItemInfo(self.item_id)

		if not success:
			return "Unexpected error when fetching item info: {}".format(info), "ERROR"

		if (int(info['bestPrice']) <= self.max_price and int(info['bestPrice']) > 0):
			if (int(info['bestPrice']) < self.min_price):
				return "PRICE BELOW THRESHOLD! (price was {})".format(info['bestPrice']), "WAIT" 

			# we found an item in our range. attempt to buy it.
			message = "Item found for {}".format(info['bestPrice'])

			success, ret = self.botClient.purchaseItem(
				info['productId'], info['bestPrice'], info['sellerId'], info['userAssetId']
			)

			if not success:
				return message + str(ret), "ERROR"

			# try to convert the response to JSON
			try:
				purchaseData = ret.json()
			except:
				return message + " No JSON response: {}".format(ret), "ERROR"

			# extract purchase status
			try:
				if purchaseData['TransactionVerb'] == 'bought':
					message += "\nPurchased!"
					return message, "PURCHASED"
				else:
					message += "\nUnable to purchase. Log: " + str(purchaseData)
					return message, "ERROR"
			except:
				message += "\nUnable to purchase. Log: " + str(purchaseData)
				return message, "ERROR"

		else:
			return "Best price is: {}".format(info['bestPrice']), "WAIT"


	def restartSession(self):
		"""Restarts the session used by the bot.
		
		This should be called when the bot returns an error or unexpected
		event.
		"""

		self.botClient = MarketAPI()
		self.botClient.startSessionNoLogin()
		self.botClient.changeCookie(self.cookie)
	

	def run(self):
		"""Starts running the bot.

		This method will block (it is intended to be used as a thread).
		"""

		self.sendToDiscord(
			"@here Logged in as " + str(self.botClient.getCurrentUser()) +
			", sniping " + self.item_name +
			" for " + str(self.max_price) + "." + " (min={})".format(self.min_price))

		self.last_update = time.time() - self.log_interval
		self.checks = 0
		self.sniped = 0

		# main loop
		while True:
			message, status = self.checkAndSnipe()

			if (status == "ERROR"):
				self.restartSession()
				self.sendToDiscord("ERROR " + message + " (while sniping " + self.item_name + ")")
			elif (status == "PURCHASED"):
				self.sendToDiscord("@here " + message + "(while sniping " + self.item_name + ")")
				self.sniped += 1
			elif (status == "WAIT"):
				if (abs(time.time() - self.last_update) >= self.log_interval):
					checks_per_second = float(self.checks) / abs(time.time() - self.last_update)
					self.checks = 0
					self.sendToDiscord("Sniping {}. {}. {} sniped so far. Average rate = {} per second.".format(
						self.item_name, message, self.sniped, checks_per_second
					))
					self.last_update = time.time()

			self.checks += 1


	def sendToDiscord(self, message):
		"""Logs a message and sends it to Discord.
		
		Parameters
		----------
		message : str
			the message to log
		"""

		print(message)

		data = {
			"content" : str(message)
		}

		self.botClient.check_session.post(self.discord_webhook, data=data)


def threadToSnipe(cookie, item_id, max_price, min_price, discord_webhook, log_interval):
	"""Entry point for a new thread.

	This function will block (it is intended to be used as a thread).

	Parameters
	----------
	cookie : str
		the cookie of the account used to make purchases
	item_id : str
		the ID of the item the bot is sniping
	max_price : int
		the maximum price to purchase the item for
	min_price : int
		the minimum price to purchase the item for
	discord_webhook : str
		the webhook of the discord bot that will log messages
	log_interval : float
		the interval between log messages, in seconds
	"""

	itemSnipeThread = ItemSnipe(cookie, item_id, max_price, min_price, discord_webhook, log_interval)
	itemSnipeThread.run()


def processSnipe(snipeItems, cookie, discord_webhook, log_interval):
	"""Entry point for a new process.

	This function will block and is intended to be run inside a separate process.

	Parameters
	----------
	snipeItems : dict
		a dictionary mapping item ID to min and max price (specifies which items
		to snipe)
	cookie : str
		the cookie of the account used to make purchases
	discord_webhook : str
		the webhook of the discord bot that will log messages
	log_interval : float
		the interval between log messages, in seconds
	"""

	for item_id, price_range in snipeItems:
		threading.Thread(target=threadToSnipe, 
			args=(cookie, item_id, price_range[1], price_range[0], discord_webhook, log_interval)
			).start()
		# wait a second before starting a new thread to avoid overloading discord
		# rate limits
		time.sleep(1)


def main():
	# load config
	with open("config.json") as json_config_file:
		config = json.load(json_config_file)
	
	items = list(config["items"].items())

	cookie = config["cookie"]
	discord_webhook = config["discord_webhook"]
	log_interval = config["log_interval"]

	# split up the items equally to separate processes, with each running a thread
	# for each item

	if config["max_processes"]:
		num_processes = len(items)
	else:
		num_processes = config["processes"]

	process_size = len(items) // num_processes
	processes = []

	for process_items in [items[x:x+process_size] for x in range(0, len(items), process_size)]:
		process = multiprocessing.Process(target=processSnipe,
			args=(process_items, cookie, discord_webhook, log_interval))
		processes.append(process)
		process.start()


if __name__ == "__main__":
	main()
