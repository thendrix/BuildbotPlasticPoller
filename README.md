# BuildbotPlasticPoller
Buildbot 8.x Plastic SCM Poller

This is a dead-simple method to hook up Plastic SCM to a buildbot 8 master server to handle push events.  It does support multiple branches per repo to save polling time.

I was hoping to get some time to clean this up before release, however here is the non-generic last used python "module" from a working buildbot 8 master.  There is no way for me to test changes past the initial commit as I migrated that project to git.

## Usage
Add these lines to master.cfg

```python
from plasticscmpoller import PlasticPoller
```

```python
c['change_source' = [
   PlasticPoller(repourl='GameRepo', branches=['main'], pollinterval=60)
]
```
