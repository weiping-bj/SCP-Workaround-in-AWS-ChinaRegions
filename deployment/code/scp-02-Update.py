import json
import boto3
import ast
import os, sys, logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    regionName = os.environ['AWS_REGION']
    boundaryFilePath = os.environ['BOUNDARY_FILE_PATH']
    topicArn = os.environ['TOPIC_ARN']
    tableName = os.environ['TABLE_NAME']
    
    ACCOUNT_ID = event['ACCOUNT_ID']
    # need scp account access
    s3_client = boto3.client('s3', region_name=regionName)
    
    BoundaryFile_BUCKET = boundaryFilePath.split('/')[2]
    BoundaryFile_OBJECT = '/'.join(boundaryFilePath.split('/')[3:])
    s3_client.download_file(BoundaryFile_BUCKET, BoundaryFile_OBJECT, '/tmp/scpBoundary.json')
    
    ddb_resource =  boto3.resource('dynamodb', region_name=regionName)
    table = ddb_resource.Table(tableName)
    
    s3_client.download_file(event['scpPermission_PATH'].split('/')[2], '/'.join(event['scpPermission_PATH'].split('/')[3:]), '/tmp/scpPermission.json')
    boundaryFilePath = "/tmp/scpBoundary.json"
    permissionFilePath = "/tmp/scpPermission.json"
    policyFilePath = '/tmp/scpPolicy.json'
    managedPolicyLimit = 6144
    scpPermission = json.load(open(permissionFilePath, 'r'))['Statement']
    with open(boundaryFilePath, 'r') as r:
        template = json.load(r)
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
            assumeRoleARN = "arn:aws-cn:iam::" + ACCOUNT_ID + ":role/" + os.environ['ASSUMED_ROLE']   
            sts_client = boto3.client('sts', region_name=regionName)
            Credentials = sts_client.assume_role(
                RoleArn=assumeRoleARN,
                RoleSessionName="SCPLoginAccount",
                DurationSeconds=900)
            iam_client = boto3.client(
                'iam',
                aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
                aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
                aws_session_token=Credentials['Credentials']['SessionToken'])
            PolicyDocument = json.load(open(policyFilePath))
            scpPolicy_response = iam_client.create_policy_version(
                PolicyArn= "arn:aws-cn:iam::" + ACCOUNT_ID + ":policy/scpPolicy",
                PolicyDocument=json.dumps(PolicyDocument),
                SetAsDefault=True
            )
            currentTime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            s3_Path = event['scpPermission_PATH']
            table.update_item(
                Key={'AccountId': ACCOUNT_ID},
                UpdateExpression='SET scpPermissionsPolicy_Path.#versionTime =:versionPath',
                ExpressionAttributeNames={"#versionTime": currentTime},
                ExpressionAttributeValues={":versionPath": s3_Path})
            message = {
                "AccountId": ACCOUNT_ID,
                "Status": "SCP plolicy has been updated",
                "New SCP Policy": event['scpPermission_PATH']
            }
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