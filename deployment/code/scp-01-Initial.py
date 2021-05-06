import json
import boto3
import botocore
import ast
import os, sys, logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    regionName = os.environ['AWS_REGION']
    boundaryFilePath = os.environ['BOUNDARY_FILE_PATH']
    eventPatternFilePath = os.environ['EVENT_PATTERN']
    rolePolicyFilePath = os.environ['ROLE_POLICY']
    trustIdentityFilePath = os.environ['ROLE_TRUST_IDENTITY']
    s3PolicyFilePath = os.environ['S3_POLICY']
    topicArn = os.environ['TOPIC_ARN']
    tableName = os.environ['TABLE_NAME']
    
    ACCOUNT_ID = event['ACCOUNT_ID']
    SCP_ACCOUNT_ID = boto3.client('sts').get_caller_identity().get('Account')
    # need scp account access
    s3_client = boto3.client('s3', region_name=regionName)
    
    BoundaryFile_BUCKET = boundaryFilePath.split('/')[2]
    BoundaryFile_OBJECT = '/'.join(boundaryFilePath.split('/')[3:])
    s3_client.download_file(BoundaryFile_BUCKET, BoundaryFile_OBJECT, '/tmp/scpBoundary.json')
    s3_client.download_file(eventPatternFilePath.split('/')[2], '/'.join(eventPatternFilePath.split('/')[3:]), '/tmp/eventRuleEventPattern.json')
    s3_client.download_file(rolePolicyFilePath.split('/')[2], '/'.join(rolePolicyFilePath.split('/')[3:]), '/tmp/eventRuleRolePolicy.json')
    s3_client.download_file(trustIdentityFilePath.split('/')[2], '/'.join(trustIdentityFilePath.split('/')[3:]), '/tmp/eventRuleRoleTrustRelation.json')
    s3_client.download_file(s3PolicyFilePath.split('/')[2], '/'.join(s3PolicyFilePath.split('/')[3:]), '/tmp/trailS3BucketPolicy.json')
    
    ddb_resource =  boto3.resource('dynamodb', region_name=regionName)
    table = ddb_resource.Table(tableName)
    
    if "scpPermission_PATH" not in event or event['scpPermission_PATH'] is '' :
        policyFilePath = '/tmp/scpBoundary.json'
        message = createProResource(ACCOUNT_ID, SCP_ACCOUNT_ID, policyFilePath)
        updateSCPResource(ACCOUNT_ID, SCP_ACCOUNT_ID)
        scpPermissionsPolicy_Path = {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()): boundaryFilePath}
        table.put_item(
            Item={
                    'AccountId': ACCOUNT_ID,
                    'scpBoundaryPolicy_Path': boundaryFilePath,
                    'scpPermissionsPolicy_Path': scpPermissionsPolicy_Path
            })
    else:
        s3_client.download_file(event['scpPermission_PATH'].split('/')[2], '/'.join(event['scpPermission_PATH'].split('/')[3:]), '/tmp/scpPermission.json')
        boundaryFilePath = "/tmp/scpBoundary.json"
        permissionFilePath = "/tmp/scpPermission.json"
        policyFilePath = '/tmp/scpPolicy.json'
        managedPolicyLimit = 6144
        scpPermission = json.load(open(permissionFilePath, 'r'))['Statement']
        with open(boundaryFilePath, 'r') as r:
            template = json.load(r)
            print(template)
            for statement in scpPermission:
                template['Statement'].append(statement)
            template = str(template).replace("<ACCOUNT_ID>",ACCOUNT_ID)
            templateStr = template.split(' ')
            Num = 0
            for alpha in templateStr:
                Num = Num + len(alpha)
            if Num <= managedPolicyLimit:
                with open(policyFilePath, 'w') as w:
                    template = ast.literal_eval(template)
                    json.dump(template, w, indent=2)
                w.close()
                message = createProResource(ACCOUNT_ID, SCP_ACCOUNT_ID, policyFilePath)
                updateSCPResource(ACCOUNT_ID, SCP_ACCOUNT_ID)
                scpPermissionsPolicy_Path = {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()): event['scpPermission_PATH']}
                table.put_item(
                    Item={
                            'AccountId': ACCOUNT_ID,
                            'scpBoundaryPolicy_Path': os.environ['BOUNDARY_FILE_PATH'],
                            'scpPermissionsPolicy_Path': scpPermissionsPolicy_Path
                    })
            else:
                message = { "Error": "The total size of each managed policy cannot exceed 6,144 characters."}
        r.close()
    sns_client = boto3.client('sns', region_name=regionName)
    sns_client.publish(
        TopicArn=topicArn,
        Subject=ACCOUNT_ID,
        Message=json.dumps(message, indent=2))
        
    return {
        'statusCode': 200
    }  
    
def createProResource(accountId, scpAccountId, scpPolicyFile):
    regionName = os.environ['AWS_REGION']
    # need pro account access
    assumedRole = os.environ['ASSUMED_ROLE']
    ACCOUNT_ID = accountId        
    assumeRoleARN = "arn:aws-cn:iam::" + ACCOUNT_ID + ":role/" + assumedRole    
    sts_client = boto3.client('sts', region_name=regionName)
    Credentials = sts_client.assume_role(
        RoleArn=assumeRoleARN,
        RoleSessionName="SCPLoginAccount",
        DurationSeconds=900)
    
    # create iam scpPolicy
    iam_client = boto3.client(
        'iam',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])
    
    PolicyDocument = json.load(open(scpPolicyFile))
    scpPolicy_response = iam_client.create_policy(
        PolicyName='scpPolicy',
        PolicyDocument=json.dumps(PolicyDocument),
        Tags=[
            {
                'Key': 'Owner',
                'Value': 'SCP-Supervisor'
            },
        ]
    )
    
    # create trail in pro account
    s3_pro_client = boto3.client(
        's3',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])
    
    ct_pro_client = boto3.client(
        'cloudtrail',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])
    
    bucketName = "scp-trail-do-not-delete-" + ACCOUNT_ID
    s3_response = s3_pro_client.create_bucket(
        ACL='private',
        Bucket=bucketName,
        CreateBucketConfiguration={
            'LocationConstraint': 'cn-north-1'
        })
    s3_pro_client.put_public_access_block(
        Bucket=bucketName,

        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        },
    )
    s3_pro_client.put_bucket_tagging(
        Bucket=bucketName,
        Tagging={
            'TagSet': [
                {
                    'Key': 'Owner',
                    'Value': 'SCP-Supervisor'
                },
            ]
        }
    )
    with open('/tmp/trailS3BucketPolicy.json', 'r') as r:
        policy = json.load(r)
        policy = str(policy).replace("<ACCOUNT_ID>",ACCOUNT_ID)
        policy = json.dumps(ast.literal_eval(policy))
    r.close()
    s3_pro_client.put_bucket_policy(Bucket=bucketName,Policy=policy)
    trailName = "scp-trail-" + ACCOUNT_ID
    try:
        trail_response = ct_pro_client.create_trail(Name=trailName,S3BucketName=bucketName,IsMultiRegionTrail=True)
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'TrailAlreadyExistsException':
            logger.warning('TrailAlreadyExistsException')
    
    ct_pro_client.add_tags(
        ResourceId=trail_response['TrailARN'],
        TagsList=[
            {
                'Key': 'Owner',
                'Value': 'SCP-Supervisor'
            }]
    )
    
    ct_pro_client.start_logging(Name=trailName)
    
    # create EventBridge Rule in pro Account
    with open('/tmp/eventRuleRolePolicy.json', 'r') as r:
        policy = json.load(r)
        policy = str(policy).replace("<SCP_ACCOUNT_ID>",scpAccountId)
        policy = json.dumps(ast.literal_eval(policy))
    r.close()
    iam_policy_response = iam_client.create_policy(
        PolicyName='scp-event-rules-policy',
        PolicyDocument=policy,
        Tags=[
            {
                'Key': 'Owner',
                'Value': 'SCP-Supervisor'
            }
        ]
    )
    iamTrust = json.load(open('/tmp/eventRuleRoleTrustRelation.json'))
    iam_role_response = iam_client.create_role(
        RoleName="scp-event-role",
        AssumeRolePolicyDocument=json.dumps(iamTrust),
        Tags=[
                {
                    'Key': 'Owner',
                    'Value': 'SCP-Supervisor'
                }
            ]
    )
    iam_client.attach_role_policy(RoleName=iam_role_response['Role']['RoleName'],PolicyArn=iam_policy_response['Policy']['Arn'])
    
    eventRulesName = "scpEvents-DO-NOT-DELETE-" + ACCOUNT_ID
    eb_client = boto3.client(
        'events',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])
    eventRule_response = eb_client.put_rule(
        Name=eventRulesName,
        EventPattern=json.dumps(json.load(open('/tmp/eventRuleEventPattern.json'))),
        State='ENABLED',
        Tags=[
                {
                    'Key': 'Owner',
                    'Value': 'SCP-Supervisor'
                },
            ]
    )
    
    SCPEventBusArn = "arn:aws-cn:events:cn-north-1:" + scpAccountId + ":event-bus/scp-bus"
    
    eb_client.put_targets(
        Rule=eventRulesName,
        Targets=[
            {
                'Id': "sendEvents",
                'Arn': SCPEventBusArn,
                'RoleArn': iam_role_response['Role']['Arn']
            }
        ]
    )
    
    iam_client.tag_role(
        RoleName=assumedRole,
        Tags=[
                {
                    'Key': 'Owner',
                    'Value': 'SCP-Supervisor'
                },
            ]
    )
    
    message = {
        "IAM Policy": [scpPolicy_response['Policy']['Arn'], iam_policy_response['Policy']['Arn']],
        "IAM Role": iam_role_response['Role']['Arn'],
        "S3 Bucket": s3_response['Location'],
        "CloudTrail Trail": trail_response['TrailARN'],
        "EventBridge Rule": eventRule_response['RuleArn']
    }
    return message

def updateSCPResource(accountId, scpAccountId):
    regionName = os.environ['AWS_REGION']
    ARN = 'arn:aws-cn:iam::' + accountId + ':root'
    eventBusName = 'scp-bus'
    # update event bus
    eb_client = boto3.client('events', region_name=regionName)
    eb_bus_policy = ast.literal_eval(eb_client.describe_event_bus(Name=eventBusName)['Policy'])
    if type(eb_bus_policy['Statement'][0]['Principal']['AWS']) is str:
        currentAccount = eb_bus_policy['Statement'][0]['Principal']['AWS']
        eb_bus_policy['Statement'][0]['Principal']['AWS'] = [currentAccount, ARN]
    else:
        eb_bus_policy['Statement'][0]['Principal']['AWS'].append(ARN)
    new_policy = str(eb_bus_policy).replace('\'', '\"')
    eb_client.put_permission(EventBusName=eventBusName,Policy=new_policy)
    
    # update event rule
    rulesEventPattern = json.loads(eb_client.describe_rule(Name='scp-rule',EventBusName='scp-bus')['EventPattern'])
    if 'account' in rulesEventPattern:
        rulesEventPattern['account'].append(accountId)
    else:
        rulesEventPattern['account'] = [accountId]
    EventPattern=str(rulesEventPattern).replace('\'', '\"')
    EventPattern=EventPattern.replace('False', 'false')
    eb_client.put_rule(
        Name='scp-rule',
        EventBusName='scp-bus',
        EventPattern=EventPattern,
        State='ENABLED'
    )

    return {
        'statusCode': 200
    }    