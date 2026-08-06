#!/usr/bin/env python3
from pathlib import Path


def load(path: str) -> tuple[Path, str]:
    file_path = Path(path)
    return file_path, file_path.read_text(encoding="utf-8")


def save(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def insert_before(path: str, marker: str, addition: str) -> None:
    file_path, text = load(path)
    if addition.strip() in text:
        return
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: marker count for {marker!r} is {text.count(marker)}")
    save(file_path, text.replace(marker, addition + marker, 1))


def insert_after_in(path: str, start_marker: str, marker: str, addition: str) -> None:
    file_path, text = load(path)
    start = text.index(start_marker)
    position = text.index(marker, start) + len(marker)
    next_function = text.find("\n}", start)
    if next_function >= 0 and position > next_function:
        raise RuntimeError(f"{path}: marker escaped function {start_marker!r}")
    region = text[start:next_function]
    if addition.strip() in region:
        return
    save(file_path, text[:position] + addition + text[position:])


def insert_before_return(path: str, start_marker: str, addition: str) -> None:
    file_path, text = load(path)
    start = text.index(start_marker)
    position = text.index("return error;", start)
    line_start = text.rfind("\n", start, position) + 1
    region = text[start:position]
    if addition.strip() in region:
        return
    save(file_path, text[:line_start] + addition + text[line_start:])


insert_before(
    "fs/exec.c",
    "static int do_execveat_common(",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,
                               void *argv, void *envp, int *flags);
#endif

""",
)
insert_after_in(
    "fs/exec.c",
    "static int do_execveat_common(",
    "{",
    """
#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
#endif""",
)

insert_before(
    "fs/open.c",
    "long do_faccessat(",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
                                int *mode, int *flags);
#endif

""",
)
insert_after_in(
    "fs/open.c",
    "long do_faccessat(",
    "unsigned int lookup_flags = LOOKUP_FOLLOW;",
    """

#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif""",
)

insert_before(
    "fs/stat.c",
    "int vfs_statx(",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_stat(int *dfd, const char __user **filename_user,
                           int *flags);
extern void ksu_handle_newfstat_ret(unsigned int *fd,
                                    struct stat __user **statbuf_ptr);
#if defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_COMPAT_STAT64)
extern void ksu_handle_fstat64_ret(unsigned long *fd,
                                   struct stat64 __user **statbuf_ptr);
#endif
#endif

""",
)
insert_after_in(
    "fs/stat.c",
    "int vfs_statx(",
    "unsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;",
    """

#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_stat(&dfd, &filename, &flags);
#endif""",
)
insert_before_return(
    "fs/stat.c",
    "SYSCALL_DEFINE2(newfstat,",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_newfstat_ret(&fd, &statbuf);
#endif
""",
)
insert_before_return(
    "fs/stat.c",
    "SYSCALL_DEFINE2(fstat64,",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_fstat64_ret(&fd, &statbuf);
#endif
""",
)

insert_before(
    "kernel/reboot.c",
    "/*\n * Reboot system call:",
    """#ifdef CONFIG_KSU_MANUAL_HOOK
extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd,
                                 void __user **arg);
#endif

""",
)
insert_after_in(
    "kernel/reboot.c",
    "SYSCALL_DEFINE4(reboot,",
    "int ret = 0;",
    """

#ifdef CONFIG_KSU_MANUAL_HOOK
        ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);
#endif""",
)

insert_after_in(
    "fs/notify/fanotify/fanotify.c",
    "struct fanotify_event_info *fanotify_alloc_event(",
    "gfp_t gfp = GFP_KERNEL_ACCOUNT;",
    """
	struct mem_cgroup *old_memcg;""",
)

drm_irq_path, drm_irq_text = load("drivers/gpu/drm/drm_irq.c")
qcom_irq_flags = "unsigned long sh_flags = IRQF_PERF_CRITICAL;"
upstream_irq_flags = "unsigned long sh_flags = 0;"
if upstream_irq_flags not in drm_irq_text:
    if drm_irq_text.count(qcom_irq_flags) != 1:
        raise RuntimeError("DRM IRQ flags marker mismatch")
    save(drm_irq_path, drm_irq_text.replace(qcom_irq_flags, upstream_irq_flags, 1))

cgroup_path, cgroup_text = load("kernel/cgroup/cgroup.c")
cgroup_start = cgroup_text.index("static int cgroup_add_file(")
cgroup_return = cgroup_text.index("return 0;", cgroup_start)
cgroup_addition = """        /* Android uses noprefix; Droidspaces/LXC also probes canonical names. */
        if (cft->ss && (cgrp->root->flags & CGRP_ROOT_NOPREFIX) &&
            !(cft->flags & CFTYPE_NO_PREFIX)) {
                snprintf(name, CGROUP_FILE_NAME_MAX, "%s.%s",
                         cft->ss->name, cft->name);
                kernfs_create_link(cgrp->kn, name, kn);
        }

"""
if cgroup_addition.strip() not in cgroup_text[cgroup_start:cgroup_return]:
    line_start = cgroup_text.rfind("\n", cgroup_start, cgroup_return) + 1
    save(cgroup_path, cgroup_text[:line_start] + cgroup_addition + cgroup_text[line_start:])

vgem_path, vgem_text = load("drivers/gpu/drm/vgem/vgem_drv.c")
fs_context_include = "#include <linux/fs_context.h>\n"
ramfs_include = "#include <linux/ramfs.h>"
if fs_context_include.strip() not in vgem_text:
    if vgem_text.count(ramfs_include) != 1:
        raise RuntimeError("vgem ramfs include marker mismatch")
    vgem_text = vgem_text.replace(
        ramfs_include,
        fs_context_include + ramfs_include,
        1,
    )

old_features = "DRIVER_GEM | DRIVER_PRIME,"
new_features = "DRIVER_GEM | DRIVER_PRIME | DRIVER_RENDER,"
if new_features not in vgem_text:
    if vgem_text.count(old_features) != 1:
        raise RuntimeError("vgem driver_features marker mismatch")
    vgem_text = vgem_text.replace(old_features, new_features, 1)
save(vgem_path, vgem_text)

selinuxfs_path, selinuxfs_text = load("security/selinux/selinuxfs.c")
static_status_ops = "static const struct file_operations sel_handle_status_ops = {"
exported_status_ops = "const struct file_operations sel_handle_status_ops = {"
if exported_status_ops not in selinuxfs_text.splitlines():
    if selinuxfs_text.count(static_status_ops) != 1:
        raise RuntimeError("sel_handle_status_ops declaration marker mismatch")
    save(
        selinuxfs_path,
        selinuxfs_text.replace(static_status_ops, exported_status_ops, 1),
    )
