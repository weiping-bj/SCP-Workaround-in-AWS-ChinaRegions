# Architecture Design

[中文](Architecture-CHN.md) ｜ English

## Architecture Briefing
When user creating an IAM entity (IAM User or IAM Role), a Lambda function is triggered by this event. The lambda function will associate a permission boundary (an IAM Policy) to the created IAM entity to control its maximum available permissions. The architecture draft is illustrated in the following diagram: 
![DesignDraft](png/01-DesignDraft.png "DesignDraft")

However, we still need to pay attention to the following three key issues if we plan to deploy this solution in a production system:

1. When an IAM entity is created with AdminFullAccess, or IAMFullAccess, how to protect above solution from being deleted (e.g., users use their Admin permissions to delete lambda functions, or remove permission boundaries that are associated with them, etc.)
2. Enterprises that need SCP functions often have multiple accounts, how to achieve unified management of multiple accounts? And ensure that permission boundaries can be set for different accounts from the unified platform?
3. When more and more production accounts are managed by a central admin account, how to track which kind of permission policy are used by different accounts?

To solve the above three key points, some AWS services are adopted: 

- Amazon API Gateway
- Amazon S3 
- Amazon EventBridge
- Amazon DynamoDB 
- Amazon SNS
- Amazon DynamoDB  

The whole architecture is as follows:  
![02-Architecture](png/02-Architecture.png "Architecture")

Admin Account is used to deploy and configure related administrative resources.  
Pro Account is a managed account that requires permission restrictions through SCP functionality.

## Admin Account 
The function of Admin Account: 

1. To initialize a Pro Account, need to create the following resources in **Pro Account**:
	- S3 Bucket: Prerequisite of creating Cloudtrail trail
	- Cloudtrail Trail: To capture IAM events when an IAM entity is created
	- EventBridge Rule: To pass filtered events to the Event Bus in Admin Account
	- IAM Policy: Policies that need to be attached to all newly created IAM entities

2. To manage the permission boundary policies used by Pro Account, you need to create the following resources in **Admin Account**:
	- S3 Bucket: To store all configuration files, and the policy files needed when creating an IAM Policy in Pro Account
	- DynamoDB Table: To record the attaching information between the Pro Account and the policy file
	
3. Receiving events from the Pro Account in order to trigger the Lambda function to automatically attach control policies, the following resources need to be created in the **Admin Account**:
	- EventBridge Bus: To allow receiving IAM events from Pro Account
	- EventBridge Rule: To filter events of IAM entities creation (CreateUser and CreateRole)

4. To achieve the automation of the above functionality, the following resources need to be created in **Admin Account**:
	- API Gateway:
		- ini: Environment initialization in Pro Account
		- update: Update permission boundary policy
	- Lambda:
		- scpIni: Environment initialization in Pro Account, triggered by ```ini``` API
		- scpUpdate: Update permission boundary policy, triggered by ```update``` API
		- scpBoundary: Associating a policy boundary to an IAM entity in a Pro Account, triggered by an IAM event in the Pro Account
	- SNS (optional): Send information email to System Operator

## Pro Account
Pro Account is used to host the production system where the maximum privileges of the IAM entity are controlled by the Admin Account. The following resources need to be deployed in the Pro Account (all of the following resources are required unless specified):

1. IAM Role, created in Pro Account:  
	- adminRole (recommeded): Full administrative access, System Operator can get all administrative privileges of Pro Account by switch role from Admin Account
	- scpRole: The scpBoundary lambda function will assume this role when excecution

2. Created by scpIni lambda function in **Admin Account**: 
	- S3 Bucket: Prerequisite of creating Cloudtrail trail
	- Cloudtrail Trail: To capture IAM events when an IAM entity is created
	- EventBridge Rule: To pass filtered events to the Event Bus in Admin Account
	- IAM Policy: Policies that need to be attached to all newly created IAM entities

## Permissions Boundary Policy
In order to control the permissions of IAM entities in Pro Account, you need to set the Permissions Boundary for IAM entities through the Lambda function in Admin Account.

The intersection of the permission boundary policy and IAM policy determines the actual permissions held by the IAM entity, as described in detail in [official docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)：  
![EffectPermissions](png/03-EffectPermissions.png "EffectPermissions")

In this solution, the permission boundary policy has two functions:

1. Limit the maximum permission boundary for all IAM entities in the Pro Account;
2. Protect the management resources in Pro Account from being destroyed.

The first part varies according to different Pro Accounts, and the second part is the same for all Pro Accounts. Therefore, in this workaround solution, the permission boundary policy is divided into two different json files:

1. scp-boundary: Statements of which resources are protected, which is normally not changed
2. scp-permission：Statements of permission boundaries for IAM entities in Pro Account, administrator writes this json file according to the standard IAM policy specification based on the actual requirements

<mark>The permissions boundary policy that is finally attached to the IAM entity: **scpPolicy = scpBoundary + scpPermission**</mark>

This solution provides a complete scp-boundary policy file and an example scp-permission policy file.

- [scpBoundaryPolicy.json](resources/s3-scp-boundary/scpBoundaryPolicy.json): Protects the administrative resources in the Pro Account. The policy contains mainly three following permission:

	- Prohibit any operations against resources tagged with ```Owner: SCP-Supervisor```;
	- Prohibit any modifications to the ```arn:aws-cn:iam::<ACCOUNT_ID>:policy/scpPolicy``` policy;
	- Allow any other operations (since the policy is associated to the IAM entity as a permissions boundary, all other operations must be explicitly allowed)

- [test-cloudtrail-deny.json](resources/s3-scp-permission/test-cloudtrail-deny.json): this policy file disables all CloudTrail operations.

## Lambda Functions

### scp-01-Initial

You may check the source code from [here](../deployment/code/scp-01-Initial.py).  

After calling ```scp/ini```, the Lambda function will be triggered to create the required administrative resources in the Pro Account. The processing logic of this function is as follows:  
![CodeDesign-ini](png/05-CodeDesign-ini.png "CodeDesign-ini")

### scp-02-Update

You may check the source code from [here](../deployment/code/scp-02-Update.py).  

After calling ```scp/update```, the Lambda function will be triggered to update permissions boundary policy in the Pro Account. The processing logic of this function is as follows:   
![CodeDesign-update](png/06-CodeDesign-update.png "CodeDesign-update")

### scp-03-Permission

You may check the source code from [here](../deployment/code/scp-03-Permission.py).  

Both IAM events (CreateUser and CreateRole) could trigger this function, which automatically attaching the permissions boundary policy. The processing logic of this function is as follows:  

![CodeDesign-permission](png/05-CodeDesign-permission.png "CodeDesign-permission")

[Return README-ENG](../README-ENG.md)