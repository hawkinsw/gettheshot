#!/bin/env python3

import requests
import json

from typing import List, Iterator
from http.client import HTTPConnection

class AvailabilitySearch():
	def __init__(self, vaccineData: str) -> None:
		self.vaccineData = vaccineData

	def results(self) -> Iterator[dict]:
		url: str = "https://api.gettheshot.coronavirus.ohio.gov/public/locations/search"
		json_params = {"location":{"lat":40.4385989,"lng":-80.7768613},"fromDate":"2021-04-07", "locationQuery":{"includePools":["default"]},"doseNumber":1,"url":"https://gettheshot.coronavirus.ohio.gov/location-select"}
		json_params['vaccineData'] = self.vaccineData

		accept: str = "application/json, text/plain, */*"
		content_type: str = "application/json;charset=utf-8"

		headers: dict = {}
		headers['accept'] = accept
		headers['content-type'] = content_type

		response = requests.post(url, headers=headers, json=json_params)
		parsed_response: dict = json.loads(response.content)

		locations = parsed_response['locations']
		if locations == None:
			return iter({})

		# TODO: Document (possibly rename)
		def cleanup_api_result(location: dict) -> dict:
			return {\
				'name': location['name'],\
				'address': location['displayAddress'],\
				'start': None if location['startDate'] == 'null' else location['startDate'],\
				'end': None if location['endDate'] == 'null' else location['endDate'],\
				}

		return map(cleanup_api_result, locations)

class VaccineData():
	def __init__(self) -> None:
		pass
	def get(self) -> str:
		url: str = "https://api.gettheshot.coronavirus.ohio.gov/public/eligibility"
		json_params: dict = {"eligibilityQuestionResponse":[{"id":"q.screening.booking.on.behalf","value":"No","type":"single-select"},{"id":"q.screening.firstname","type":"text"},{"id":"q.screening.lastname","type":"text"},{"id":"q.ineligible.registration.email","type":"email"},{"id":"q.screening.phonenumber","type":"mobile-phone"},{"id":"q.screening.relation","type":"single-select"},{"id":"q.screening.eligibility.question.1","value":"Yes","type":"single-select"},{"id":"q.screening.accessibility.code","type":"text"},{"id":"q.screening.initialconsent","value":["consent.initial.text"],"type":"multi-select"},{"id":"q.screening.acknowledge.vaccine","value":["acknowledgement.text"],"type":"multi-select"}],"url":"https://gettheshot.coronavirus.ohio.gov/screening"}

		accept: str = "application/json, text/plain, */*"
		content_type: str = "application/json;charset=utf-8"

		headers: dict = {}
		headers['accept'] = accept
		headers['content-type'] = content_type

		response = requests.post(url, headers=headers, json=json_params)
		parsed_response = json.loads(response.content)

		vaccineData: str = ""
		if parsed_response['vaccineData'] != None:
			vaccineData = parsed_response['vaccineData']

		return vaccineData

if __name__ == "__main__":
	vd = VaccineData()

	# First, get a vaccineData value.
	vaccineData = vd.get()

	search = AvailabilitySearch(vaccineData)

	for i in search.results():
		print(repr(i))
