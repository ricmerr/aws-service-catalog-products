import logging
import boto3
import os
import json

boto_level = os.environ.get("BOTO_LOG_LEVEL", logging.CRITICAL)
logging.getLogger("boto").setLevel(boto_level)
logging.getLogger("boto3").setLevel(boto_level)
logging.getLogger("botocore").setLevel(boto_level)
logging.getLogger("urllib3").setLevel(boto_level)

log_level = os.environ.get("LOG_LEVEL", logging.WARNING)
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(levelname)s %(threadName)s %(message)s", level=logging.INFO
)
logger.setLevel(log_level)


def get_detector_id(client):
    paginator = client.get_paginator('list_detectors')
    for page in paginator.paginate():
        for detector_id in page.get("DetectorIds", []):
            logger.debug(f"Looking at {detector_id}")
            detector = client.get_detector(
                DetectorId=detector_id
            )
            logger.debug(f"Checking detector: {detector.get('Status')}")
            if detector.get("Status") == "ENABLED":
                return detector_id
    logger.info("Did not find an enabled detector")
    return None


def create_detector(client):
    response = client.create_detector(
        Enable=True,
        ClientToken='foundational-aws-guardduty-multi-account',
        FindingPublishingFrequency='FIFTEEN_MINUTES',
        DataSources={
            'S3Logs': {
                'Enable': True
            }
        },
    )
    logger.info("created a detector")
    return response.get("DetectorId")


def update_organization_configuration(client, detector_id):
    if client.describe_organization_configuration(DetectorId=detector_id).get("AutoEnable", False) is not True:
        logger.info("AutoEnabled was not enabled")
        client.update_organization_configuration(
            DetectorId=detector_id,
            AutoEnable=True,
            DataSources={
                'S3Logs': {
                    'AutoEnable': True
                }
            }
        )
        logger.info("AutoEnabled set to true")


def enable_organization_admin_account(client, admin_account_id):
    client.enable_organization_admin_account(
        AdminAccountId=admin_account_id
    )


def is_an_organization_admin_accounts(client, account_id):
    paginator = client.get_paginator('list_organization_admin_accounts')
    for page in paginator.paginate():
        for admin_accounts in page.get("AdminAccounts", []):
            if admin_accounts.get("AdminAccountId") == account_id:
                return admin_accounts.get("AdminStatus") == "ENABLED"
    return False


def make_an_organization_admin_accounts(client, account_id):
    client.enable_organization_admin_account(
        AdminAccountId=account_id
    )
    logger.info(f"made {account_id} an org admin account")


def get_org_client(region):
    guard_duty_multi_account_delegate_admin_role_arn = os.environ.get(
        "GUARD_DUTY_MULTI_ACCOUNT_DELEGATE_ADMIN_ROLE_ARN")
    sts = boto3.client('sts')
    assumed_role_object = sts.assume_role(
        RoleArn=guard_duty_multi_account_delegate_admin_role_arn,
        RoleSessionName='guard_duty_multi_account_delegate_admin_role_arn',
    )
    credentials = assumed_role_object['Credentials']
    kwargs = {
        "aws_access_key_id": credentials['AccessKeyId'],
        "aws_secret_access_key": credentials['SecretAccessKey'],
        "aws_session_token": credentials['SessionToken'],
    }
    return boto3.client('guardduty', region_name=region, **kwargs)


def create_client(region):
    return boto3.client('guardduty', region_name=region)


def ensure_all_are_members(client, detector_id, accounts_to_ensure):
    client.create_members(
        DetectorId=detector_id,
        AccountDetails=[{
            'AccountId': account_to_ensure.get("account_id"),
            'Email': account_to_ensure.get("email")
        } for account_to_ensure in accounts_to_ensure]
    )
    logger.info(f"created members")


def handle(event, context):
    logger.info("starting")
    logger.debug(json.dumps(event, default=str))
    region = event.get("region")
    account_id = event.get("account_id")
    accounts_to_ensure = event.get("accounts_to_ensure", [])

    guardduty = create_client(region)
    detector_id = get_detector_id(guardduty)
    if detector_id is None:
        detector_id = create_detector(guardduty)

    org_client = get_org_client(region)
    if not is_an_organization_admin_accounts(org_client, account_id):
        logger.info(f"{account_id} is not an org admin account")
        make_an_organization_admin_accounts(org_client, account_id)

    update_organization_configuration(guardduty, detector_id)
    ensure_all_are_members(guardduty, detector_id, json.loads(accounts_to_ensure))
    logger.info("created")


if __name__ == "__main__":
    os.environ[
        'GUARD_DUTY_MULTI_ACCOUNT_DELEGATE_ADMIN_ROLE_ARN'] = 'arn:aws:iam::156551640785:role/foundational/GuardDutyMultiAccount/DelegateAdminRole'
    sample_parameters = dict(
        region="eu-west-1",
        account_id="338024302548",
        accounts_to_ensure=json.dumps([
            {"account_id": "156551640785", "email": "eamonnf+SCT-demo-hub@amazon.co.uk"},
            {"account_id": "029953558454", "email": "eamonnf+SCT-demo-spoke-5@amazon.co.uk"},
            {"account_id": "511601033246", "email": "eamonnf+SCT-demo-spoke-4@amazon.co.uk"},
            {"account_id": "574018543153", "email": "eamonnf+SCT-demo-spoke-3@amazon.co.uk"},
            {"account_id": "338024302548", "email": "eamonnf+SCT-demo-spoke-2@amazon.co.uk"},
        ])
    )

    sample_context = None
    handle(sample_parameters, sample_context)