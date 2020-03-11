#!/bin/bash
voice_alert=1
follow_maintenance_window=0
function run_at()
{  
    db_inst=$1
    start_time=$2

    if [[ $follow_maintenance_window -eq 0 ]]; then 
        python3 rds_ssl_update.py --restore_to_ca2015 --apply_immediate --max_sleep 180 $db
        return
    fi
    # maintenance window
    maxtime=$(date -j -v +30M -f "%H:%M:%S" $start_time +%H:%M:%S) 

    echo "Next Instance is-"
    echo $db  $start_time
    echo "Current Time: $(date +%H:%M:%S)"
    echo "Maintenance window: $start_time-$maxtime"
    echo "Next Start at: $start_time"
  
  while true; do
    
   currenttime=$(date +%H:%M:%S)    
   if [[ "$currenttime" > $start_time ]]; then
     
        #  check for currenttime +30 maintenance window
        if [[ "$currenttime" > $maxtime ]]; then
             echo "ERROR: Current time $currenttime is outside of maintenance window."
            #  say -v Daniel "ERROR: Current time is outside of maintenance window."
            break;
        fi
        echo "=> Now Running at: $currenttime"
        # cat ss.txt
        # sleep 1
        python3 rds_ssl_update.py --restore_to_ca2015 --apply_immediate --max_sleep 180 $db
        if [[ $? -ne 0 ]]; then
            alert "ALERT: Failed to update, please check logs!"
            break;
        fi
        
     break;
   else
     sleep 20
     echo -n .
    fi
  done  
}

rollback_update()
{
    for db in `cat data.txt|awk '{print $1}'`;
    do
        start_at=$(cat data.txt|grep $db|awk '{print $3}')
        # //process
        run_at $db $start_at
        # if [[ $? -ne 0 ]]; then
        #     echo $pod  "Failed." 
        #     break;
        # fi
        echo
        echo
    done
    echo "Exiting"
}

region="us-west-2"

ssl_check_status()
{
    # switch profile to dba role
    export AWS_PROFILE=predix-dba

    db_arr=()
    query='DBInstances[*].[DBInstanceIdentifier,DBSubnetGroup.DBSubnetGroupName,
                           PreferredMaintenanceWindow,CACertificateIdentifier,DBInstanceStatus]'
    echo
    echo
    echo "REGION: $region"
    echo
    if [ $# -ne 0 ]; then
        if [[ "$1" = "all" ]]; then
            aws rds describe-db-instances --query $query --output table --region $region 
        else
            aws rds describe-db-instances --db-instance-identifier $1 --query $query --output table --region $region 
      fi
    else
        i=0
         
        for db in `cat data.txt|awk '{print $1}'`; do
            db_arr+="$db,"
            ((i=i+1))
            if [ $i -gt 99 ]; then
                exec_aws_describe_db "$db_arr" $query $region
                db_arr=()
                i=0
            fi
        done
       if [ $i -gt 0 ] ; then
            exec_aws_describe_db "$db_arr" $query $region
       fi
    fi
    if [[ $? -ne 0 ]]; then
        echo  "Failed to get details for. " $db
    fi
    
    echo "Exiting"
}

exec_aws_describe_db()
{
    db_ids_str=$1
    # Remove last , from list of instances
    if [[ "${db_ids_str: -1}" == "," ]]; then 
        db_ids_str=${db_ids_str: : -1}    
    fi
    
   aws rds describe-db-instances --filter Name=db-instance-id,Values=$db_ids_str \
            --query $2 --output table --region $3 #\| egrep --color -E '^|available' 
}
 


alert()
{
    msg=$1
    echo $msg
    echo
    maxwait=5
    pause=0
    echo "HIT [enter] key to pause ... or 'c' and then 'enter' to continue."
    echo "..It will auto continue in $maxwait sec."
    k=0
    while [ true ] ; do
        read -t 3 k 
       case $k in
            c* )     break;;
            "" )     pause=1 ; echo; echo  "Paused, Hit 'c' and then 'enter' to continue.";k=0;;
        esac
            if [[ $pause -eq 0 ]]; then
                if [[ $voice_alert -eq 1 ]]; then
                    say -v Daniel $msg
                fi
                if [[ $maxwait -eq 0 ]]; then 
                    break
                else
                    maxwait=$(($maxwait-1))
                    echo -n "..$maxwait"
                fi
            fi
         
    done
}
# ssl_run_update
# ssl_check_status

# DB_INST=db-504de2a6-11fe-46e6-9a66-e83192d3b101
# aws rds describe-db-instances --db-instance-identifier $DB_INST\
#     --query 'DBInstances[*].[DBInstanceIdentifier,
#                             DBSubnetGroup.DBSubnetGroupName,
#                             CACertificateIdentifier,
#                             PreferredMaintenanceWindow]' \
#     --output text 