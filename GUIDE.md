创空间自己有一个仓库链接，需要添加。把<创空间仓库URL>换成实际的创空间仓库地址。modelscope 是这个仓库的别名。

``` bash
git remote add modelscope <创空间仓库URL>
```

确保当前处于 master 分支：

``` bash
# 切换到 master 分支
git checkout master
```


抓取远程仓库 main 分支的更新：

``` bash
# 临时保存之前的本地更改
git add .
git stash

# 拉取更新
git fetch --all

# 这条命令的意思是：把本地 master 的内容变成和远程 main 一模一样
# 这样 master 永远能得到最新的开发成果
git reset --hard origin/main

# 还原之前的本地更改，如果看到 CONFLICT ，需要解决一下冲突
git stash pop
```


推送：
``` bash
git add .
git commit -m "你的提交信息"
git push origin master       # 推送到 GitHub 备份（推送到 master 分支而非 main 分支）
git push modelscope master   # 向创空间上线部署
```