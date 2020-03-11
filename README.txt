Demo Files

Source 

git clone https://github.com/AWS-POCs/rds_ssl_update_automation.git


Tools needed.

asciinema -- to play demo recoding
python3 -- to run python script
aws cli -- to talk to aws resources.


--To play demo recoding.
python script
asciicena play demo_python_ssl_update
asciicena play demo_automation

-- To run python script.

python3 rds_ssl_update.py --apply_immediate --max_sleep 180 db-12323233-bfd1-4879-a1c0-e36d02272129
python3 rds_ssl_update.py --max_sleep 180 db-c0b39e70-bfd1-4879-23243-e36d02272129
python3 rds_ssl_update.py --restore_to_ca2015 --apply_immediate --max_sleep 180 db-323423-bfd1-4879-a1c0-e36d02272129

-- To run automation

$ source ssl_rds.sh
$ ssl_check_status
$ ssl_run_update

