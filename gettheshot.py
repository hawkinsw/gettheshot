#!/bin/env python3

import requests
import json
import csv
import time
import sys
from datetime import datetime

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

# Assume that each vaccination appointment lasts 30 minutes
minutes_per_appt = 30
# Assume that there is one dose per appointment
doses_per_appt = 1

class SearchResult():
  startDate: Optional[str]
  endDate: Optional[str]
  url: Optional[str]
  doses: int
  displayAddress: str
  name: str

  def __init__(self, name: str,
                     displayAddress: str,
                     startDate: Optional[str],
                     endDate: Optional[str],
                     doses: int,
                     url: Optional[str]):
    self.name = name
    self.displayAddress = displayAddress
    self.startDate = startDate
    self.endDate = endDate
    self.doses = doses
    self.url = url

  def __repr__(self) -> str:
    return self.name + ": " +\
    self.displayAddress + " has " + \
    repr(self.doses) + " doses (" +\
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
      logging.basicConfig()
      logging.getLogger().setLevel(logging.DEBUG)
      requests_log = logging.getLogger("urllib3")
      requests_log.setLevel(logging.DEBUG)
      requests_log.propagate = True

    parsed_response: Optional[dict] = None
    try:
      response: Optional[Response] = None
      response = requests.post(url, headers=headers, json=json_params)
      parsed_response = json.loads(response.content)
    except Exception as e: pass

    # Check for errors
    if not parsed_response or not 'locations' in parsed_response:
      print("Failed to search!")
      return []

    def api_output_to_search_result(location: dict) -> SearchResult:
      location_doses = 0

      # This loop calculates the number of doses available at this location.
      #
      # Each location has an array of open hours. Those are the hours and
      # days that the location is open with vaccines available. The fields
      # for each entry in the array are:
      # 1. days: The days of the week for which the _localStart_ and
      # _localEnd_ apply
      # 2. localStart: The time that the vaccination center opens on the days
      # in _days_.
      # 3. localStart: The time that the vaccination center closes on the days
      # in _days_.
      #
      # We assume that the location schedules minutes_per_appt appointments
      # and that they can give out doses_per_appt doses per appointment.
      for open_hour_entry in location['openHours']:
        # each entry in the openHours could represent more than 1 day.
        open_hour_day_count = len(open_hour_entry['days'])

        # convert the start time to a datetime (for manipulation)
        open_hour_start_time = datetime.strptime(
          open_hour_entry['localStart'],
          "%H:%M:%S")
        # convert the end time to a datetime (for manipulation)
        open_hour_end_time = datetime.strptime(
          open_hour_entry['localEnd'],
          "%H:%M:%S")
        # Take the difference between the start and the end time (in seconds)
        # convert that to minutes (/60) and then convert that to appt chunks
        # (/minutes_per_appt). That will be the number of appointments
        # available. Finally, convert that to doses per day (*doses_per_appt).
        open_hour_doses_per_day = (
          int((open_hour_end_time - open_hour_start_time).total_seconds()
          /60
          /30)
          *doses_per_appt)

        """
        print("location:", json.dumps(location))
        print("days:", json.dumps(open_hour_entry['days']))
        print("open_hour_doses_per_day: ", open_hour_doses_per_day)
        print("open_hour_day_count: ", open_hour_day_count)
        """

        location_doses += (
          open_hour_doses_per_day *
          open_hour_day_count)

      return SearchResult(location['name'],
        location['displayAddress'],
        None if location['startDate'] == 'null' else location['startDate'],
        None if location['endDate'] == 'null' else location['endDate'],
        location_doses,
        None if not 'externalURL' in location else location['externalURL'],
      )

    return [i for i in map(api_output_to_search_result,
                           parsed_response['locations'])]

class VaccineData():
  def __init__(self) -> None:
    pass
  def get(self) -> Optional[str]:
    url: str = "https://api.gettheshot.coronavirus.ohio.gov/public/eligibility"
    json_params: dict = {"eligibilityQuestionResponse":[{"id":"q.screening.booking.on.behalf","value":"No","type":"single-select"},{"id":"q.screening.firstname","type":"text"},{"id":"q.screening.lastname","type":"text"},{"id":"q.ineligible.registration.email","type":"email"},{"id":"q.screening.phonenumber","type":"mobile-phone"},{"id":"q.screening.relation","type":"single-select"},{"id":"q.screening.eligibility.question.1","value":"Yes","type":"single-select"},{"id":"q.screening.accessibility.code","type":"text"},{"id":"q.screening.initialconsent","value":["consent.initial.text"],"type":"multi-select"},{"id":"q.screening.acknowledge.vaccine","value":["acknowledgement.text"],"type":"multi-select"}],"url":"https://gettheshot.coronavirus.ohio.gov/screening"}

    accept: str = "application/json, text/plain, */*"
    content_type: str = "application/json;charset=utf-8"

    headers: dict = {}
    headers['accept'] = accept
    headers['content-type'] = content_type

    try:
      response = requests.post(url, headers=headers, json=json_params)
      parsed_response = json.loads(response.content)

      vaccine_data: Optional[str] = None
      if parsed_response['vaccineData'] != None:
        vaccine_data = parsed_response['vaccineData']

      return vaccine_data
    except Exception as e:
      return None

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

  max_results_cutoff: Optional[int] = None #25
  unique_results: Dict[str, dict] = {}
  locations: List[ZipLatLng] = []
  vd: VaccineData = VaccineData()

  # First, get a vaccineData value.
  vaccineData: Optional[str] = vd.get()

  if not vaccineData:
    print("Oops: Could not get a valid vaccine data string.")
    sys.exit(1)

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
  # NOTE: Remember that this will require local AWS credentials to work.
  # Be sure to configure these credentials with `aws configure`.
  aws_client = boto3.client('s3')
  try:
    aws_client.upload_file('results.json', aws_bucket, aws_key)
  except (S3UploadFailedError, ClientError) as e:
    print("Error uploading to s3: " + repr(e))
  else:
    print("Success uploading to s3.")
  sys.exit(0)
