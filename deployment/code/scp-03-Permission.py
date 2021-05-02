import json
import os
import boto3

topicArn = os.environ['TOPIC_ARN']
assumedRole = os.environ['ASSUMED_ROLE']
scpBoundary = os.environ['SCP_BOUNDARY_POLICY']


sns_client = boto3.client('sns')
sts_client = boto3.client('sts')

def lambda_handler(event, context):
    print(event)
    
    accountID = event['account']
    assumeRoleARN = "arn:aws-cn:iam::" + accountID + ":role/" + assumedRole
    Credentials = sts_client.assume_role(
        RoleArn=assumeRoleARN,
        RoleSessionName="LoginAccount",
        DurationSeconds=900)
    print(Credentials)
    
    SCP_BOUNDARY =  "arn:aws-cn:iam::" + accountID + ":policy/" + scpBoundary
    
    if event['detail']['userIdentity']['type'] == "IAMUser":
        Creator_Name = event['detail']['userIdentity']['userName']
        Creator_Type = "USER"
    elif event['detail']['userIdentity']['type'] == "AssumedRole":
        Creator_Name = event['detail']['userIdentity']['sessionContext']['sessionIssuer']['userName']
        Creator_Type = "ROLE"    
    # 判断，User 和 Role 分别处理
    if event['detail']['eventName'] == "CreateUser":
        identityArn, rspAction = processUser(event, SCP_BOUNDARY, Creator_Name, Creator_Type, Credentials)
        Operation_Type="IAM User Creation"
    elif event['detail']['eventName'] == "CreateRole":
        identityArn, rspAction = processRole(event, SCP_BOUNDARY, Creator_Name, Creator_Type, Credentials)
        Operation_Type="IAM Role Creation"
    else:
        print("Others")
    # 发 SNS 通知消息
    output = {
        "Operation Type": Operation_Type, 
        "Identity ARN": identityArn,
        "Creator Type": Creator_Type,
        "Creator Name": Creator_Name,
        "Respond Action": rspAction}
    
    print(output)

    sns_client.publish(
        TopicArn=topicArn,
        Subject=Operation_Type,
        Message=json.dumps(output, indent=2))
    
    return {
        'statusCode': 200
    }

def processRole(event, boundaryArn, creatorName, creatorType, Credentials):
    Role_Arn = event['detail']['responseElements']['role']['arn']
    Role_Name = Role_Arn.split('/')[-1]
    
    
    iam_client = boto3.client(
        'iam',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])
    
    iam_client.put_role_permissions_boundary(
        RoleName=Role_Name,
        PermissionsBoundary=boundaryArn
    )
    
    Role_Info = iam_client.get_role(RoleName=Role_Name)['Role']['AssumeRolePolicyDocument']['Statement'][0]['Principal']
    if "Federated" in Role_Info:
        trustedIdt = "Federated"
    elif "Service" in Role_Info:
        trustedIdt = Role_Info['Service'].split('.')[-3]
    else:
        trustedIdt = Role_Info['AWS'].split(':')[4]
    iam_client.tag_role(
        RoleName=Role_Name,
        Tags=[
            {
                'Key': 'Creator Name',
                'Value': creatorName
            },
            {
                'Key': 'Creator Type',
                'Value': creatorType
            },
            {
                'Key': 'Trusted Identi',
                'Value': trustedIdt
            }
        ]
    )
    Action="Tagged"
    return Role_Arn, Action
    
def processUser(event, boundaryArn, creatorName, creatorType, Credentials):
    User_Name = event['detail']['responseElements']['user']['userName']
    User_Arn = event['detail']['responseElements']['user']['arn']
    
    iam_client = boto3.client(
        'iam',
        aws_access_key_id=Credentials['Credentials']['AccessKeyId'],
        aws_secret_access_key=Credentials['Credentials']['SecretAccessKey'],
        aws_session_token=Credentials['Credentials']['SessionToken'])

    iam_client.put_user_permissions_boundary(
        UserName=User_Name,
        PermissionsBoundary=boundaryArn
    )
    
    iam_client.tag_user(
        UserName=User_Name,
        Tags=[
            {
                'Key': 'Creator Name',
                'Value': creatorName
            },
            {
                'Key': 'Creator Type',
                'Value': creatorType
            }
        ]
    )
    Action = "Tagged"
    return User_Arn, Action