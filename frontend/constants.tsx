
import { Task, NodeGroup, TaskStatus } from './types';

export const INITIAL_TASKS: Task[] = [
  {
    id: 1,
    node: NodeGroup.NODE1,
    title: "Network Configuration",
    instructions: "Configure the network interface with IP address 192.168.122.10/24, gateway 192.168.122.1, and DNS 8.8.8.8. Set hostname to node1.example.com.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 2,
    node: NodeGroup.NODE1,
    title: "BaseOS/AppStream Repos",
    instructions: "Configure local yum repositories for BaseOS and AppStream. Use /mnt/BaseOS and /mnt/AppStream as sources.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 3,
    node: NodeGroup.NODE1,
    title: "SELinux Web Port",
    instructions: "Configure the Apache web server to run on port 82. Ensure SELinux allows this port.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 4,
    node: NodeGroup.NODE1,
    title: "Users & Group Creation",
    instructions: "Create a group named 'sysadmin'. Create users 'alice' and 'bob', and add them to the 'sysadmin' group.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 5,
    node: NodeGroup.NODE1,
    title: "Shared Directory",
    instructions: "Create a directory /home/shared. Ensure it is owned by the group 'sysadmin' and has g+rwx permissions. Implement setgid.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 6,
    node: NodeGroup.NODE1,
    title: "autofs NFS",
    instructions: "Configure autofs to automatically mount an NFS export from server.example.com:/export/home to /rhome/remote_user.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 7,
    node: NodeGroup.NODE1,
    title: "Cron Job",
    instructions: "Create a cron job for user 'alice' that runs 'logger \"Hello World\"' every day at 14:23.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 8,
    node: NodeGroup.NODE1,
    title: "NTP Client",
    instructions: "Configure chronyd to sync with pool.ntp.org.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 9,
    node: NodeGroup.NODE1,
    title: "Find Files by Owner",
    instructions: "Find all files owned by user 'alice' in /etc and copy them to /root/alice_files/.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 10,
    node: NodeGroup.NODE1,
    title: "Find Strings",
    instructions: "Search for all lines containing 'rhcsa' in /usr/share/dict/words and save them to /root/lines.txt.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 11,
    node: NodeGroup.NODE1,
    title: "User with UID",
    instructions: "Create a user 'charlie' with UID 2000.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 12,
    node: NodeGroup.NODE1,
    title: "Archive Creation",
    instructions: "Create a bzip2 compressed tar archive of /etc named /root/etc.tar.bz2.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 13,
    node: NodeGroup.NODE1,
    title: "Container Service",
    instructions: "Run a podman container using the 'nginx' image and configure it as a systemd user service for user 'alice'.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 14,
    node: NodeGroup.NODE1,
    title: "Default Permissions",
    instructions: "Set the umask for all new users to 007.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 15,
    node: NodeGroup.NODE2,
    title: "Root Password",
    instructions: "Reset the root password to 'redhat'.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 16,
    node: NodeGroup.NODE2,
    title: "Repositories",
    instructions: "Configure YUM repositories for NODE2 using the provided URL.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 17,
    node: NodeGroup.NODE2,
    title: "Resize LV",
    instructions: "Resize the logical volume 'vo' to 300MB without losing data.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 18,
    node: NodeGroup.NODE2,
    title: "Swap Creation",
    instructions: "Add a 512MB swap partition to the system and ensure it persists across reboots.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 19,
    node: NodeGroup.NODE2,
    title: "Create LV",
    instructions: "Create a logical volume named 'data' in volume group 'vg0' with a size of 10 extents.",
    status: TaskStatus.IDLE,
    lastCheck: null
  },
  {
    id: 20,
    node: NodeGroup.NODE2,
    title: "tuned profile",
    instructions: "Set the system tuned profile to 'virtual-guest'.",
    status: TaskStatus.IDLE,
    lastCheck: null
  }
];
