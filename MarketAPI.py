import requests
from bs4 import BeautifulSoup
import requests.cookies
import re
import json


# load config
with open('api-config.json') as json_config_file:
	config = json.load(json_config_file)


class MarketAPI(object):
	"""
	A class used to represent an API interface for the bot.

	...

	Attributes
    ----------
    session : requests.Session
        the main session with account cookies
	check_session : requests.Session
		a session used to access API endpoints where a logged in
		user is not needed (ex. checking item price)
    xsrf_token : str
        cached value of the most recent "X-CSRF-TOKEN" header received
    username : str
		the username of the current logged in account
	userId : str
		the user ID of the current logged in account

    Methods
    -------
    startSessionNoLogin()
        Creates the Session instances for the bot.
	changeCookie(cookie)
		Changes the account cookie for the bot to use.
	getCurrentUser()
		Gets the username and user ID of the current account using this bot.
	getMarketItemInfo(itemId)
		Gets information about an item on the marketplace.
	purchaseItem(productId, price, sellerId, userAssetId)
		Attempts to purchase an item from the marketplace.
	getOwnedAssets(itemId)
		Gets all copies of an item the current account owns.
	sellItem(itemId, userAssetId, price)
		Sells an item on the marketplace for the specified price.
	getAssetNameFromId(assetId)
		Gets the asset name of a particular asset by its ID.
	getProductId(assetId)
		Gets the product ID of a particular asset by its ID.
	"""


	def __init__(self):
		"""Creates a new MarketAPI obj.
		"""

		pass


	def startSessionNoLogin(self):
		"""Creates the Session instances for the bot.

		Two sessions are created: the main session which is used to access
		endpoints where an authenticated account is needed (ex. purchasing an
		item), and a session used to access endpoints where no account is
		needed (ex. checking the price of an item).
		"""

		self.session = requests.session()
		self.check_session = requests.session()

		self.xsrf_token = ""


	def changeCookie(self, cookie):
		"""Changes the account cookie for the bot to use.

		If another account was previously using the bot, the old cookie
		is discarded and no further requests will be made using it.
		
		Parameters
		----------
		cookie : str
			the cookie of the account to use
		"""

		self.session.cookies[config["account_cookie_name"]] = cookie
		self.username, self.userId = self.getCurrentUser()


	def getCurrentUser(self):
		"""Gets the username and user ID of the current account using this bot.
		
		Returns
		----------
		str
			the username of the current account, or None if no account was
			found
		str
			the user ID of the current account, or None if no account was
			found
		"""

		html = self.session.get(config["home_url"]).text
		matches = re.search("data-name=([a-zA-Z_0-9]+)", html)
		try:
			username = matches.group(1)
		except:
			return None, None

		matches = re.search("data-userid=([0-9]+)", html)
		try:
			userId = matches.group(1)
		except:
			return username, None
		
		return username, userId
	

	def getMarketItemInfo(self, itemId):
		"""Gets information about an item on the marketplace.
		
		The information about the item concerns its current lowest price,
		and the account selling it. The information returned is enough
		to immediately purchase the item (without any additional API calls).

		Parameters
		----------
		itemId : str
			the item ID of the limited item

		Returns
		----------
		boolean
			indicates if the operation succeeded
		str or dict
			if operation was not successful, the error message is returned.
			if the operation was successful, a dict is returned containing:
				"bestPrice" : <int : the current lowest price of the item>,
				"sellerId" : <str : the user ID of the seller of the item>,
				"productId" : <str : the product ID of the item>,
				"userAssetId" : <str : the item's asset ID>
		"""

		itemId = int(itemId)

		try:
			html = self.check_session.get(config["base_url"] + "/catalog/" + str(itemId), timeout=5).text
		except:
			return False, "Error when fetching item page."

		soup = BeautifulSoup(html, features="html.parser")
		itemContainer = soup.find('div', {'id' : 'item-container'})
		if itemContainer is None:
			return False, "Page had no item-container element."

		if int(itemContainer["data-item-id"]) != itemId:
			return False, "Unexpected item id: expected {}, received {}".format(itemId, itemContainer["data-item-id"])

		bestPrice = str(itemContainer["data-expected-price"])

		try:
			bestPrice = int(bestPrice)
		except:
			return False, "Unexpected price: {}".format(bestPrice)

		sellerId = str(itemContainer["data-expected-seller-id"])
		productId = str(itemContainer["data-product-id"])
		userAssetId = str(itemContainer["data-lowest-private-sale-userasset-id"])

		return True, {
			"bestPrice" : bestPrice,
			"sellerId" : sellerId,
			"productId" : productId,
			"userAssetId" : userAssetId
		}


	def purchaseItem(self, productId, price, sellerId, userAssetId):
		"""Attempts to purchase an item from the marketplace.

		The purchase request is made using the session's account cookie.

		Parameters
		----------
		productId : str
			the product ID of the item
		price : str
			the price of the item, as string. Should be a positive integer.
		sellerId : str
			the user ID of the seller
		userAssetId : str
			the asset ID of the item

		Returns
		----------
		boolean
			indicates if the operation succeeded
		str or requests.Response
			if operation was not successful, the error message is returned.
			if the operation was successful, the request response is returned.
		"""

		try:
			req = self.session.post(
				url = config["base_url"] + "/api/item.ashx?" + 
				"rqtype=purchase&productID={productId}&expectedCurrency=1&expectedPrice={price}&expectedSellerID={sellerId}&userAssetID={userAssetId}".format(
					productId = productId, price = price, sellerId = sellerId, userAssetId = userAssetId),
				headers = {"X-CSRF-TOKEN": self.xsrf_token}
				)
		except:
			return False, "Error when posting purchase request. Response was: {}".format(req)

		if "X-CSRF-TOKEN" in req.headers:
			# the cached token was not valid: generate a new one
			self.xsrf_token = req.headers["X-CSRF-TOKEN"]
			return self.purchaseItem(productId, price, sellerId, userAssetId)
		
		return True, req


	def getOwnedAssets(self, itemId):
		"""Gets all copies of an item the current account owns.

		Parameters
		----------
		itemId : str
			the item ID to get all owned copies of

		Returns
		----------
		boolean
			indicates if the operation succeeded
		str or list
			if operation was not successful, the error message is returned.
			if the operation was successful, a list of str is returned. Each
			element in the list is the asset ID of an owned copy of the item.
		"""

		req = None
		owned_asset_ids = []

		try:
			req = self.check_session.get(
				url = config["inventory_url"] + "/users/" + str(self.userId) + "/items/Asset/" + str(itemId)
				)

			for itemdata in req.json()["data"]:
				userAssetId = itemdata["instanceId"]
				owned_asset_ids.append(str(userAssetId))
		except:
			return False, "Unable to get owned copies of asset {}. Response was {}".format(
				itemId, owned_asset_ids
			)

		return True, owned_asset_ids


	def sellItem(self, itemId, userAssetId, price):
		"""Sells an item on the marketplace for the specified price.

		If the same item was previously put on sale for another price, this
		request will override the price. 

		Parameters
		----------
		itemId : str
			the item ID of the item to sell
		userAssetID : str
			the asset ID of the item to sell
		price : str
			the price to sell the item at

		Returns
		----------
		boolean
			indicates if the operation succeeded
		str or requests.Response
			if operation was not successful, the error message is returned.
			if the operation was successful, the request response is returned.
		"""

		try:
			req = self.session.post(
				url = config["base_url"] + "/asset/toggle-sale?" + 
				"assetId={itemId}&userAssetId={userAssetId}&price={price}&sell={sell}".format(
					itemId=itemId, userAssetId=userAssetId, price=price, sell=True),
				headers={"X-CSRF-TOKEN": self.xsrf_token}
				)
		except:
			return False, "Error when selling an item. Response was: {}".format(req)

		if "X-CSRF-TOKEN" in req.headers:
			self.xsrf_token = req.headers["X-CSRF-TOKEN"]
			return self.sellItem(itemId, userAssetId, price)

		return True, req


	def getAssetNameFromId(self, assetId):
		"""Gets the asset name of a particular asset by its ID.

		Parameters
		----------
		assetId : str
			the asset ID of asset
		
		Returns
		----------
		str
			the name of the asset
		"""

		parameters = {
			"assetId" : assetId
		}

		return self.check_session.get(config["marketplace_api"] + "/productinfo", params=parameters).json()["Name"]


	def getProductId(self, assetId):
		"""Gets the product ID of a particular asset by its ID.

		Parameters
		----------
		assetId : str
			the asset ID of asset
		
		Returns
		----------
		str
			the product ID of the asset
		"""

		req = self.check_session.get(config["marketplace_api"] + "/productinfo?assetId=" + str(assetId)).json()

		return req["ProductId"]
