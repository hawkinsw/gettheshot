#!/bin/env python3

import requests
import json
import csv
import time

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import ClientError

from typing import List, Iterator, Optional, Dict
try:
    from typing import TypedDict  # >=3.8
except ImportError:
    from mypy_extensions import TypedDict  # <=3.7

from http.client import HTTPConnection
import logging

class SearchResult():
  startDate: Optional[str]
  endDate: Optional[str]
  url: Optional[str]
  displayAddress: str
  name: str

  def __init__(self, name: str,
                     displayAddress: str,
                     startDate: Optional[str],
                     endDate: Optional[str],
                     url: Optional[str]):
    self.name = name
    self.displayAddress = displayAddress
    self.startDate = startDate
    self.endDate = endDate
    self.url = url

  def __repr__(self) -> str:
    return self.name + ": " +\
    self.displayAddress + " (" +\
    repr(self.startDate) + ", " +\
    repr(self.endDate) + ") @ " +\
    repr(self.url)

class AvailabilitySearch():
  def __init__(self, vaccineData: str,
                     lat: float,
                     lng: float) -> None:
    self.lat = lat
    self.lng = lng
    self.vaccineData = vaccineData

  def results(self) -> List[SearchResult]:
    debug: bool = False;
    url: str = "https://api.gettheshot.coronavirus.ohio.gov/public/locations/search"
    json_params = {"location":{"lat": self.lat, "lng": self.lng },"fromDate":"2021-04-07", "locationQuery":{"includePools":["default"]},"doseNumber":1,"url":"https://gettheshot.coronavirus.ohio.gov/location-select"}
    json_params['vaccineData'] = self.vaccineData

    accept: str = "application/json, text/plain, */*"
    content_type: str = "application/json;charset=utf-8"

    headers: dict = {}
    headers['accept'] = accept
    headers['content-type'] = content_type

    # Debugging
    if debug:
      HTTPConnection.debuglevel = 1
      logging.basicConfig() # you need to initialize logging, otherwise you will not see anything from requests
      logging.getLogger().setLevel(logging.DEBUG)
      requests_log = logging.getLogger("urllib3")
      requests_log.setLevel(logging.DEBUG)
      requests_log.propagate = True

    response = requests.post(url, headers=headers, json=json_params)
    parsed_response: dict = json.loads(response.content)

    if not 'locations' in parsed_response:
      return []

    locations = parsed_response['locations']
    # TODO: Document (possibly rename)
    def api_output_to_search_result(location: dict) -> SearchResult:
      return SearchResult(location['name'],
        location['displayAddress'],
        None if location['startDate'] == 'null' else location['startDate'],
        None if location['endDate'] == 'null' else location['endDate'],
        None if not 'externalURL' in location else location['externalURL'],
      )

    return [i for i in map(api_output_to_search_result, locations)]

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

class ZipLatLng(TypedDict):
  zipcode: str
  lat: float
  lng: float

def toJSONSerializable(frm: object) -> dict:
  return frm.__dict__

if __name__ == "__main__":
  # Configuration options for uploading to s3
  aws_bucket: str = "vaccine-availability"
  aws_key:str = "gettheshot.json"

  max_results_cutoff: Optional[int] = 25
  unique_results: Dict[str, dict] = {}
  locations: List[ZipLatLng] = []
  vd: VaccineData = VaccineData()

  # First, get a vaccineData value.
  vaccineData: str = vd.get()

  # Open the file with the zipcodes to scan.
  with open('zipcodes.csv', newline='') as zipcodes:
    zipcodereader = csv.reader(zipcodes)
    for zipcode in zipcodereader:
      # For each of the zipcodes in the file, add an entry to the
      # locations array. The locations array is what will be used
      # to determine what is scraped.
      locations.append({ 'zipcode': zipcode[0],
                         'lat': float(zipcode[1]),
                         'lng': float(zipcode[2]) })

  # For each location to be scraped ...
  for location in locations:
    print("Searching for locations near " + location['zipcode'] + " ...")

    # Search for doses near this particular location
    search = AvailabilitySearch(vaccineData, location['lat'], location['lng'])

    # For every location with a dose available
    for i in search.results():
      # Add it to a dictionary keyed by the name of the location
      # Doing this means that we can use this dictionary to ultimately
      # get a list of the locations with doses with no duplicates.
      unique_results[i.name] = toJSONSerializable(i)

      print(repr(i))

    # If we are only supposed to generate a certain number of results,
    # stop when we hit that number.
    if max_results_cutoff and len(unique_results.keys()) > max_results_cutoff:
      break

    # We sleep here because we don't want to overwhelm the API
    time.sleep(2)

  # Convert the dictionary to an array
  array_results: List[dict] = [unique_results[i] for i in unique_results.keys()]

  # Using the json format, serialize the array to disk.
  with open('results.json', mode='w+') as results:
    results.write(json.dumps(array_results))

  # Now, upload the results to s3.
  aws_client = boto3.client('s3')
  try:
    aws_client.upload_file('results.json', aws_bucket, aws_key)
  except (S3UploadFailedError, ClientError) as e:
    print("Error uploading to s3: " + repr(e))
  else:
    print("Success uploading to s3.")

