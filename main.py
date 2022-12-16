from __future__ import print_function

import json
import os.path
import base64
from bs4 import BeautifulSoup
from datetime import datetime, date

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from typing import List

from lunchable import LunchMoney
from lunchable.models import TransactionBaseObject, TransactionInsertObject, CategoriesObject, AssetsObject

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CATEGORYID = 'shared expense'
ACCOUNTNAME = 'expense'


transactionQueue: List[TransactionBaseObject] = []
transactionItem: TransactionInsertObject
transactionAccount = int
transactionAmount = int
transactionPayee = str
transactionDate = date
transactionCategory = int
transactionCurrency = "usd"
transactionNotes = str


def main():

    ### Gmail Connection###

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

        ### Connect to LunchMoney API and authenticate###

    if os.path.exists('LMToken.json'):
        Token = json.load(open('LMToken.json'))['token']
        lunch = LunchMoney(access_token=Token)

        accounts: List[AssetsObject] = lunch.get_assets()
        categories: List[CategoriesObject] = lunch.get_categories()

        for cat in categories:
            if CATEGORYID in cat.name.lower():
                transactionCategory = cat.id

        for act in accounts:
            if ACCOUNTNAME in act.display_name.lower():
                transactionAccount = act.id

    try:

        ### Call the Gmail API ###

        service = build('gmail', 'v1', credentials=creds)
        msgs = service.users().messages().list(userId='me', maxResults=300).execute()
        msgList = msgs.get('messages')

        if not msgList:
            print('Nothing found.')
            return
        print('Messages:')
        # Look at a single message with in the mailbox
        for i, msg in enumerate(msgList):
            # Make a entry
            entry = service.users().messages().get(
                userId='me', id=msg['id']).execute()

            # Identify the payload, headers, and body(encoded)
            payload = entry['payload']
            headers = payload['headers']

            # Look through the headers to find who sent it an what the subject was
            for d in headers:
                if d['name'] == 'From':
                    sender = d['value']
                    # print(sender)
                if d['name'] == 'Subject':
                    subject = d['value']
                    # print(subject)

            # Check if the sender was venmo and print out for checking
            if 'venmo' in sender.lower():
                print(sender)
                print(subject)

            # Try to get the body of the email and decode the base64 info
                try:
                    parts = payload.get('parts')[1]
                    data = parts['body']['data']
                    data = data.replace("-", "+").replace("_", "/")
                    decoded_data = base64.b64decode(data)
                    soup = BeautifulSoup(decoded_data, "html.parser")
                    # Use the decoded body to search for the table with the correct information
                    table = soup.find_all("table", id=True)[0].stripped_strings

                    for x, tab in enumerate(table):

                        if x == 2:
                            transactionPayee = tab
                            print(transactionPayee)
                        elif x == 3:
                            transactionNotes = tab
                            print(transactionNotes)
                        elif x == 5:
                            transactionDate = date.fromisoformat(datetime.strptime(
                                tab[0:12], '%b %d, %Y').isoformat()[0:10])
                            print(transactionDate)
                        elif x == 7:
                            transactionAmount = float(tab[3:])
                            print(transactionAmount)

                    transactionItem = TransactionInsertObject(
                        date=transactionDate, amount=transactionAmount, notes=transactionNotes, payee=transactionPayee, currency=transactionCurrency, category_id=transactionCategory, asset_id=transactionAccount, status='cleared')
                    print(transactionItem)
                    transactionQueue.append(transactionItem)
                except TypeError:
                    continue
                except IndexError:
                    print('Not a payment email')
                except:
                    print("Error in Payload Body")

                    continue

            else:
                print(f'Email {i}: Not Venmo')

        ### After Going through all the messages from Venmo, send the transaction queue to LunchMoney###

        new_transaction_IDS = lunch.insert_transactions(
            transactions=transactionQueue, apply_rules=True, skip_duplicates=True, skip_balance_update=False, debit_as_negative=True)
        print(new_transaction_IDS)

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f'An error occurred: {error}')


if __name__ == '__main__':
    main()
