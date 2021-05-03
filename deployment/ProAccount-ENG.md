#Deployment-in-Pro-Acount

[中文](ProAccount-CHN.md) ｜ English

##Create Resources
There is only one resource need to be created: IAM Role.  

Other administrative resources needed in the Pro Account will be created through the Lambda function [scp-01-Initial](code/scp-01-Initial.py), which is deployed in the Admin Account and triggered through the scp/ini API. During the execution of this function, the necessary permissions in the Pro Account are obtained by Assume Role. The assumed Role is a IAM Role that needs to be created manually by the user in Pro Account. The process of creation are as follows.

1. **Select type of trusted entity: Admin Account**  
Login AWS console, choose ```IAM > Roles > Create Role```, "Another AWS Account" as trusted entity, input the 12-digit AccountId of Admin Account.    
![TustIdentity](png/Pro-01-TrustIdentity.png "TrustIdentity")

2. **Attach permissions policies:**
	- AmazonS3FullAccess 
	- IAMFullAccess 
	- AmazonEventBridgeFullAccess 
	- AWSCloudTrail_FullAccess 

3. **Add Tag:**  

	Key | Value 
	----|-----
	Owner | SCP-Supervisor

4. **Name of Role: scpRole**  
Input the name of the role: ```scpRole```  
![scpRole](png/Pro-02-scpRole.png "scpRole")

##Additional Notes
Since this solution is not retroactive, it is recommended to keep only 1 IAM entity (User or Role) with ``AdministratorAccess`` permissions, in addition to the IAM entity generated when the account is created, until the production account is put into use. This additional IAM entity is used for daily operations and maintenance.

- If the Pro Account account is created through AWS Organizations, an IAM Role is automatically created within Pro account, and the trusted entity is the main AWS Organizations account with ``AdministratorAccess`` permissions.
- If the Pro Account account is created through the standard process, there will be an IAM User with ``AdministratorAccess`` in the account.

>In both regions of AWS Mainland China, users will not be granted login access via the root user email.

The administrator can use the above initial IAM entity to create a scpRole in Pro Account, and then complete the creation of other resources in Pro Account by calling scp/ini.

[Return README](../README-ENG.md)
