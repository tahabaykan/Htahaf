@echo off
title Truth Ticks Cluster Launcher
echo Starting 6-Terminal Cluster...
cd /d %~dp0
python launch_cluster.py
pause
