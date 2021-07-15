import json
import boto3
from boto3.dynamodb.conditions import Key
import os
import logging
import traceback
import sys

query_db_name = os.environ["QUERY_DB"]
prot_db_name = os.environ["PROT_DB"]
class_db_name = os.environ["CLASS_DB"]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
query_db = dynamodb.Table(query_db_name)
prot_db = dynamodb.Table(prot_db_name)
class_db = dynamodb.Table(class_db_name)

def collect_uniq_fams(families):
    fam_set = []
    fam_items_uniq = []
    for item in families:
        family = item["family"]
        if family not in fam_set:
            fam_set.append(family)
            fam_items_uniq.append({
                "family": family,
                "class": item["class"]
            })
    return fam_items_uniq

def lambda_handler(event, context):
    try:
        logger.info(f'Event: {event}')
        search = event["search"].lower()
        #search = event["search"].lower()

        dna_ids = query_db.query(
            IndexName = "dna_id_lc-index",
            KeyConditionExpression = Key("dna_id_lc").eq(search)
        )["Items"]
    
        prot_ids = query_db.query(
            IndexName = "prot_id_lc-index",
            KeyConditionExpression = Key("prot_id_lc").eq(search)
        )["Items"]
        
        families = query_db.query(
            IndexName = "fam_lc-index",
            KeyConditionExpression = Key("fam_lc").eq(search)
        )["Items"]
    
        proteins = prot_db.query(
            KeyConditionExpression = Key("protein").eq(search.capitalize())
        )["Items"]
    
        classes = class_db.query(
            KeyConditionExpression = Key("class").eq(search.upper())
        )["Items"]
        
        families = collect_uniq_fams(families)
        
        data = {
            "dna_ids": dna_ids,
            "prot_ids": prot_ids,
            "families": families,
            "proteins": proteins,
            "classes": classes
        }
        
        count = len(dna_ids) + len(prot_ids) + len(families) + len(proteins) + len(classes)
        
        logger.info(f'Search returned number of items: {count}')
    
        return {
            'status_code': 200,
            'body': data
        }

    except Exception as error:
        exception_type, exception_value, exception_traceback = sys.exc_info()
        traceback_string = traceback.format_exception(exception_type, exception_value, exception_traceback)
        err_msg = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": traceback_string
        })
        logger.error(err_msg)