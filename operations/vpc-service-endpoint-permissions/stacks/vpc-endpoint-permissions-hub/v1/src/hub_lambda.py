import boto3
from botocore.exceptions import ClientError
import logging
import traceback
from crhelper import CfnResource
import os
import json

helper = CfnResource()

# define logging
log = logging.getLogger(__name__)


@helper.create
@helper.update


def handle_response_status_and_msg(response):
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        response['responseStatus'] = 'SUCCESS'
    else:
        response['responseStatus'] = 'FAILED'
    response['statusCode'] = response['ResponseMetadata']['HTTPStatusCode']
    return response


def handle_error(event, error_message, statusCode, response_status):
    log.error(error_message, exc_info=1)
    return {
        'event': event,
        'statusCode': 400,
        'responseStatus': 'FAILED',
        #'body': error_message
        'body': json.dumps(str(error_message))
        #'body': json.dumps(traceback.format_exc())
    }


def add_permission(event, service_id, account_id):
    """
    Adds permission to the VPC Endpoint Service
    """
    log.info(f'Adding permision to a VPC Endpoint Service')
    response = []
    try:
        Principal = 'arn:aws:iam::' + account_id + ':root'
        log.info(f'Principal is {Principal}')
        log.info(f'Adding permission for {Principal} to {service_id}')
        client = boto3.client('ec2')
        response = client.modify_vpc_endpoint_service_permissions(
            DryRun=False,
            ServiceId=service_id,
            AddAllowedPrincipals=[
                Principal
            ]
        )
        # example response:
        # {'ReturnValue': True, 'ResponseMetadata': {'RequestId': '1246566a-3ca9-4a87-a8f3-6e098e6171b1', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': '1246566a-3ca9-4a87-a8f3-6e098e6171b1', 'cache-control': 'no-cache, no-store', 'strict-transport-security': 'max-age=31536000; includeSubDomains', 'vary': 'accept-encoding', 'content-type': 'text/xml;charset=UTF-8', 'transfer-encoding': 'chunked', 'date': 'Fri, 10 Dec 2021 15:10:46 GMT', 'server': 'AmazonEC2'}, 'RetryAttempts': 0}}
        # see: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/error-handling.html
        response = handle_response_status_and_msg(response)
        log.info(response)
        return response
    except ClientError as e:
        error_message = f'Error adding permission for account id {account_id} to VPC Service Endpoint {service_id}:\n{str(e)}'
        return handle_error(event, error_message, 400, 'FAILED')


def delete_permission(event, service_id, account_id):
    """
    Deletes permission to the VPC Endpoint Service
    """
    log.info(f'Deleting permision in a VPC Endpoint Service')
    response = []
    try:
        Principal = 'arn:aws:iam::'+ account_id +':root'
        log.info(f'Principal is {Principal}')
        log.info(f'Deleting permission for {Principal} in {service_id}')
        client = boto3.client('ec2')
        response = client.modify_vpc_endpoint_service_permissions(
            DryRun=False,
            ServiceId=service_id,
            RemoveAllowedPrincipals=[
                Principal
            ]
        )
        response = handle_response_status_and_msg(response)
        log.info(response)
        return response
    except ClientError as e:
        error_message = f'Error deleting permission for account id {account_id} to VPC Service Endpoint {service_id}:\n{str(e)}'
        return handle_error(event, error_message, 400, 'FAILED')


def update_permission(event, service_id, old_account_id, new_account_id):
    log.info(f'Updating permision in a VPC Endpoint Service')
    response = delete_permission(event, service_id, old_account_id)

    if response['responseStatus'] == 'SUCCESS':
        response = add_permission(event, service_id, new_account_id)
        return response
    else:
        # do not run the 2nd API call when the 1st call failed
        return response


def lambda_handler(event, context):
    try:
        log.info(event)

        # get parameters values
        service_id = os.environ['ServiceId']
        account_id = event['ResourceProperties']['AccountId']
        action = event['RequestType']
        log.info(f'ServiceId is {service_id}\nAccountId is {account_id}\nAction is {action}')

        if action == 'Create':
            response = add_permission(event, service_id, account_id)
        elif action == 'Update':
            old_account_id = event['ResourceProperties']['OldAccountId']
            response = update_permission(event, service_id, old_account_id, account_id)
        elif action == 'Delete':
            response = delete_permission(event, service_id, account_id)
        else:
            error_message = f'Unsupported action: {action}'
            return handle_error(event, error_message, 400, 'FAILED')
        return response


    except Exception as err:
        log.error(traceback.format_exc())
        return handle_error(event, traceback.format_exc(), 500, 'FAILED')