
# Get list of instances need ssl update in a region

# Switch role for aws cli to prod dba role for eg.
# define aws/config
# eg.
[profile prod-dba]
region = us-west-2
role_arn = arn:aws:sts::112233445566:role/prod-dba
mfa_serial = arn:aws:iam::665544332211:mfa/500158334
source_profile = default

export AWS_PROFILE=prod-dba


# get complete list  of 2015 db instances
aws rds describe-db-instances --region "us-west-2" \
    --query 'DBInstances[*].[DBInstanceIdentifier,
                            DBSubnetGroup.DBSubnetGroupName,
                            CACertificateIdentifier,
                            PreferredMaintenanceWindow,DBInstanceStatus]' \
     --output text | grep rds-ca-2015 
