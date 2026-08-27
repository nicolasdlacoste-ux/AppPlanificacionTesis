import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
creds = service_account.Credentials.from_service_account_file(
    'config/service-account.json', scopes=SCOPES)
delegated_creds = creds.with_subject('ndiaz@akrimet.com')
service = build('calendar', 'v3', credentials=delegated_creds)

events_result = service.events().list(calendarId='ndiaz@akrimet.com', q='test', singleEvents=True, maxResults=10).execute()
events = events_result.get('items', [])

print("Found events:")
for ev in events:
    print(ev['summary'], ev['id'], ev.get('start'), ev.get('status'))
