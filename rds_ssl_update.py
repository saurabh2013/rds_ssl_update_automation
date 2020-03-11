import boto3
import argparse
import sys
import time
import os.path
from os import path
from botocore.exceptions import ClientError
from loguru import logger


def max_sleep_type(x):
    x = int(x)
    if x <= 0:
        raise argparse.ArgumentTypeError("max_sleep value should be positive integer")
    return x


# CLI options
parser = argparse.ArgumentParser(description='Update RDS instance to use the latest ssl cert')
parser.add_argument('--restore_to_ca2015', action='store_true', help='Restore the old certificate rds-ca-2015')
parser.add_argument('--apply_immediate',  action='store_true')
parser.add_argument('--create_session_token', action='store_true', help='Creates a new session credentails file')
parser.add_argument('--cf_subnet', type=str, default='cf3', help='environment [cf3]/cf1-1')
parser.add_argument('--max_sleep', type=max_sleep_type, default=30, help='maximum sleep interval for the status check')
parser.add_argument('id', type=str, help='Provide an instance id')
args = parser.parse_args()
instance = dict()
sts_creds = dict()
iam_creds=dict()

# ANy db instance you want to skip goes here.
skip_ids=[
'db-test1-dba6-4930-8fbc-920f7116885d',
'db-test2-25b2-4665-80bd-b938547c1cc2',
'db-test3-ad60-45a7-b662-9d39594b7e1c',
]

mfa_token=''
stscli = boto3.client
rdscli = boto3.client


rds_ca_2019='rds-ca-2019'
rds_ca_2015='rds-ca-2015'
token_file='.session_token'
iam_file='.iam_config'
cf_subnet=f'lynny-wb-postgres-{args.cf_subnet}-db-subnet-group'

# Logging
logger.remove()
logger.add(sys.stdout, format="{time} {level} {message}",)

# createSessionTokenFile creates the token file, with the temporary credentails
def createSessionTokenFile(force_create=False):
    global mfa_token
    global stscli
    if path.exists(token_file):
        if force_create==False:
            logger.debug(f'{token_file} file is already exists')
            return
        else:
            logger.info(f'Creating new {token_file} file')

    try:
        mfa_token=input('Enter your mfa token value ')
        stscli = boto3.client('sts', region_name=iam_creds[0], aws_access_key_id=iam_creds[1], aws_secret_access_key=iam_creds[2], )    
        response = stscli.get_session_token(DurationSeconds=129600,SerialNumber=iam_creds[3],TokenCode=mfa_token)
        akey=response['Credentials']['AccessKeyId']
        skey=response['Credentials']['SecretAccessKey']
        sToken=response['Credentials']['SessionToken']
        
        sf=open(token_file, 'w')
        sf.writelines([f'{akey}\n', f'{skey}\n', f'{sToken}\n'])
        sf.flush()
        sf.close()
    except ClientError as e:
        # If the previous token is expired, then we may get this error
        if e.response['Error']['Code'] == 'AccessDenied':
            logger.exception(e)
            logger.warning('Seems the previous MFA token value is expired')
            mfa_token=input('Enter new MFA token value: ')
            createSessionTokenFile(True)
        else:
            logger.exception(e)
            sys.exit(1)

# loadSessionCreds read the session credentails from the token file
def loadSessionCreds():
    global sts_creds
    if path.exists(token_file):
        sf=open(token_file, 'r')
        sts_creds.clear()
        i=0
        for x in sf:
            sts_creds[i]=x.rstrip('\n')
            i=i+1
    else:
        logger.error(f'The {token_file} file do not exists to read the credentails')
        sys.exit(1)


# initRdsCli this initiates the rds cli connection
def initRdsCli():
    global sts_creds
    global mfa_token
    global rdscli
    if len(sts_creds)<3:
        logger.error('Invalid session credentails')
        sys.exit(1)
    else:
        try:
            newstscli = boto3.client('sts', region_name=iam_creds[0], aws_access_key_id=sts_creds[0],aws_secret_access_key=sts_creds[1],aws_session_token=sts_creds[2] )
            assumed_role_object=newstscli.assume_role( RoleArn="arn:aws:iam::426506953375:role/predix-dba", RoleSessionName="Session_For_RDS_SSL_Update",)

            credentials=assumed_role_object['Credentials']
            rdscli = boto3.client('rds',  region_name=iam_creds[0], aws_access_key_id=credentials['AccessKeyId'], aws_secret_access_key=credentials['SecretAccessKey'], aws_session_token=credentials['SessionToken'],)
        except Exception as e:
            logger.exception(e)
            sys.exit(1)


# Checking DB Instance status
def describeInstance():
    global instance
    global rdscli
    try:
        instance = rdscli.describe_db_instances(DBInstanceIdentifier=args.id)['DBInstances'][0]
        if not instance:
            logger.error('Instance {} is not found in the region {}'.format(args.id, iam_creds[0]))
            sys.exit(1)
            
    except Exception as e:
        logger.exception(e)
        sys.exit(1)

#Check whether the instance is in CF3 or not
def check_for_subnet()->bool:
    global instance
    if instance['DBSubnetGroup']['DBSubnetGroupName'] == cf_subnet:
        return True
    else:
        return False


def getInstanceCert()->str:
    return instance['CACertificateIdentifier']


# Check if the instance is using the latest rds-ca-2019 cert
def instanceUseLatestCert() -> bool:
    if getInstanceCert() == rds_ca_2019:
        return True
    else:
        return False


# Check if the instance is using the old rds-ca-2015 cert
def instanceUseOldCert() -> bool:
    if getInstanceCert() == rds_ca_2015:
        return True
    else:
        return False

def checkStatus(cert):
    i=1
    while i<=args.max_sleep:
        rdscli.get_waiter('db_instance_available').wait(DBInstanceIdentifier=args.id)
        describeInstance()
        if getInstanceCert() == cert:
            break
        else:
            i=i*2
            logger.debug('instance {} is not yet updated with the certificate {}. Checking status after few seconds ...'.format(args.id, cert))
            time.sleep(i)

    if getInstanceCert() == cert:
        logger.success('Instance {} is modified with the certificate {}'.format(args.id, cert))
    else:
        logger.error('Something went wrong, instance {} is not modified with the required certificate {}'.format(args.id, cert))
        logger.info('Current instance {} certificate is {}'.format(args.id,getInstanceCert()))
        logger.info('Try to re-run the same script, and see whether problem persists')

# Updating certificates
def updateCert(cert):
    global rdscli
    try:
        logger.info('Modifying the instance {} with certificate {}'.format(args.id, cert))
        rdscli.modify_db_instance(DBInstanceIdentifier=args.id, ApplyImmediately=args.apply_immediate, CACertificateIdentifier=cert)
        if (args.apply_immediate):
            checkStatus(cert)
        else:
            logger.success('Seems, certificate change to the instance {} will be applied during the next maintenance window'.format(args.id))

    except Exception as e:
        logger.exception(e)
        sys.exit(1)

def validate_cf_subnet():
    if args.cf_subnet!='cf1-1' and args.cf_subnet!='cf3':
        logger.error('Provide only cf1-1/cf3 values as case insensitive')
        sys.exit(1)

def create_iam_config():
    if not path.exists(iam_file):
        logger.debug('{} file not exists, so creating it with the values'.format(iam_file))
        region=input('Provide region ')
        akey=input('Provide ACCESS_KEY ')
        skey=input('Provide SECRECT_KEY ')
        mfa=input('Provide MFA ARN ')
        sf=open(iam_file, 'w')
        sf.writelines([f'{region}\n', f'{akey}\n', f'{skey}\n', f'{mfa}\n'])
        sf.flush()
        sf.close()
    else:
        logger.debug('{} file exists, so reading IAM details from this file'.format(iam_file))

def load_iam_config():
    global iam_creds
    if not path.exists(iam_file):
        logger.error('The {} is not exists'.format(iam_file))
        sys.exit(1)
    else:
        sf=open(iam_file, 'r')
        iam_creds.clear()
        i=0
        for x in sf:
            iam_creds[i]=x.rstrip('\n')
            i=i+1

def check_skip_ids():
    for i in skip_ids:
        if args.id == i:
            logger.error('instance {} is marked as to skip, try with the other instance id'.format(i))
            sys.exit(1)


def doAction():
    if not check_for_subnet():
        logger.error('instance {} is not of type {}, so exiting from here'.format(args.id, args.cf_subnet))
        sys.exit(1)

    if not args.restore_to_ca2015: 
        if instanceUseLatestCert():
            logger.info('Instance {} is already using the latest cert {}'.format(args.id, rds_ca_2019))
        else:
            updateCert(rds_ca_2019)
    else:
        if instanceUseOldCert():
            logger.info('Instance {} is already using the old cert {}'.format(args.id, rds_ca_2015))
        else:
            updateCert(rds_ca_2015)


validate_cf_subnet()
check_skip_ids()
create_iam_config()
load_iam_config()
createSessionTokenFile(args.create_session_token)
loadSessionCreds()
initRdsCli()
describeInstance()
doAction()