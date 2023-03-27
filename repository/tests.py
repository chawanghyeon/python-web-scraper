import os
import shutil

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from git.repo import Repo
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from fork.models import Fork
from project.settings import REPO_ROOT
from repository.models import Repository, Tag
from user.models import User


class RepositoryViewSetTestCase(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", password="user1_password"
        )
        self.user2 = User.objects.create_user(
            username="user2", password="user2_password"
        )
        self.user1_token = RefreshToken.for_user(self.user1).access_token
        self.user2_token = RefreshToken.for_user(self.user2).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.user1_token}")

        # Remove all files and directories in REPO_ROOT
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
            for file in filenames:
                os.remove(os.path.join(dirpath, file))
            for dirname in dirnames:
                shutil.rmtree(os.path.join(dirpath, dirname))

        repo_path = os.path.join(REPO_ROOT, self.user1.username, "test_repo")
        file_path = os.path.join(repo_path, "README.txt")

        repo = Repo.init(repo_path)
        open(file_path, "w").close()
        repo.index.add("*")
        repo.index.commit("initial commit")

        self.repository = Repository.objects.create(
            name="test_repo",
            user=self.user1,
            path=os.path.join(REPO_ROOT, self.user1.username, "test_repo"),
        )

        # clone repository
        repo = Repo.clone_from(
            self.repository.path,
            os.path.join(REPO_ROOT, self.user2.username, "test_repo"),
        )
        branch_name = "new-branch-name"
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()
        repo.index.add(["*"])
        repo.index.commit("initial commit")
        self.repository2 = Repository.objects.create(
            name="test_repo",
            user=self.user2,
            path=os.path.join(REPO_ROOT, self.user2.username, "test_repo"),
            fork=True,
        )

        self.fork = Fork.objects.create(
            user=self.user1,
            source_repository=self.repository2,
            target_repository=self.repository,
        )

    def test_create_repository(self):
        if os.path.exists(os.path.join(self.repository.path, "test_repo")):
            shutil.rmtree(os.path.join(self.repository.path, "test_repo"))

        response = self.client.post(
            reverse("repository-list"),
            data={"name": "test_create_repo"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Repository.objects.count(), 3)
        self.assertTrue(
            os.path.exists(
                os.path.join(REPO_ROOT, self.user1.username, "test_create_repo")
            )
        )

    def test_retrieve_repository(self):
        response = self.client.get(
            reverse("repository-detail", args=[self.repository2.id]),
        )

        self.assertTrue(response.data["tree"])
        self.assertEqual(response.status_code, 200)

    def test_retrieve_fork_repository(self):
        with open(os.path.join(self.repository2.path, "README.txt"), "w") as f:
            f.write("This is a test file.")
        repo = Repo(self.repository2.path)
        repo.index.add(["*"])
        repo.index.commit("Updated README.txt")

        response = self.client.get(
            reverse("repository-detail", args=[self.repository2.id]),
        )
        self.assertTrue(response.data["pullrequest"])
        self.assertEqual(response.status_code, 200)

    def test_partial_update(self):
        new_content = "This is some new content."
        new_file = SimpleUploadedFile("README.txt", bytes(new_content, "utf-8"))

        data = {
            "file": new_file,
            "message": "Updated README.txt",
            "path": f"{self.user1.username}/{self.repository.name}/{new_file.name}",
        }
        response = self.client.patch(
            reverse("repository-file", args=[self.repository.id]),
            data,
            format="multipart",
        )
        with open(os.path.join(self.repository.path, "README.txt"), "r") as f:
            file_content = f.read()
            self.assertIn(new_content, file_content)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        with open(os.path.join(self.repository.path, "README.txt"), "r") as f:
            file_content = f.read()
            self.assertIn(new_content, file_content)

        repo = Repo(self.repository.path)
        self.assertFalse(repo.is_dirty())
        self.assertEqual(repo.head.commit.message, data["message"])

    def test_partial_update_structure(self):
        data = {
            "structure": '{"README.txt": "blob", "test": {"README.txt": "blob"}}',
            "message": "Updated README.txt",
        }
        response = self.client.patch(
            reverse("repository-structure", args=[self.repository.id]),
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            reverse("repository-detail", args=[self.repository.id]),
        )
        self.assertEqual(response.data["tree"], data["structure"])

    def test_destroy_repository(self):
        response = self.client.delete(
            reverse("repository-detail", args=[self.repository.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Repository.objects.count(), 1)
        self.assertFalse(os.path.exists(self.repository.path))

    def test_list_repositories(self):
        Repository.objects.bulk_create(
            [
                Repository(
                    name=f"test_repo{i}",
                    user=self.user1,
                    path=f"temp{i}",
                    star_count=i,
                )
                for i in range(10)
            ]
        )

        response = self.client.get(
            reverse("repository-list"),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertEqual(response.data["results"][0]["name"], "test_repo9")

    def test_list_repositories_by_tag(self):
        tag1 = Tag.objects.create(name="test1")

        repositories = Repository.objects.bulk_create(
            [
                Repository(
                    name=f"test_repo{i}",
                    user=self.user1,
                    path=f"temp{i}",
                    star_count=i,
                )
                for i in range(10)
            ]
        )

        for repository in repositories:
            repository.tags.add(tag1)

        response = self.client.get(
            reverse("repository-tag"),
            data={"tag": "test1"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)

    def test_update_name(self):
        data = {
            "old_name": "README.txt",
            "new_name": "AFTER.txt",
            "message": "test_update",
        }
        response = self.client.patch(
            reverse("repository-rename", args=[self.repository.id]),
            data,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(os.path.exists(os.path.join(self.repository.path, "AFTER.txt")))

    def test_create_branch(self):
        data = {"branch_name": "test_branch", "message": "test_create_branch"}
        response = self.client.post(
            reverse("repository-branch", args=[self.repository.id]),
            data,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.repository.path, ".git", "refs", "heads", "test_branch"
                )
            )
        )

    def test_destory_branch(self):
        self.test_create_branch()

        data = {"branch_name": "test_branch", "message": "test_delete_branch"}
        repo = Repo(self.repository.path)
        repo.git.checkout("main")

        response = self.client.delete(
            reverse("repository-branch", args=[self.repository.id]),
            data,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    self.repository.path, ".git", "refs", "heads", "test_branch"
                )
            )
        )

    def test_update_branch(self):
        self.test_create_branch()

        data = {"branch_name": "main", "message": "test_update_branch"}

        response = self.client.patch(
            reverse("repository-branch", args=[self.repository.id]),
            data,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Repo(self.repository.path).active_branch.name == "main")

    def test_list_branches(self):
        self.test_create_branch()

        response = self.client.get(
            reverse("repository-branch", args=[self.repository.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_working_tree(self):
        self.test_partial_update()

        response = self.client.get(
            reverse("repository-workingtree", args=[self.repository.id])
            + f"?commit_hash={Repo(self.repository.path).head.commit.hexsha}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_commits(self):
        self.test_partial_update()

        response = self.client.get(
            reverse("repository-commit", args=[self.repository.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_rollback_to_commit(self):
        self.test_partial_update()

        repo = Repo(self.repository.path)
        commit_hash = repo.head.commit.parents[0].hexsha

        data = {"commit_hash": commit_hash, "message": "test_rollback_to_commit"}
        response = self.client.put(
            reverse("repository-rollback", args=[self.repository.id]),
            data,
            format="json",
        )

        with open(os.path.join(self.repository.path, "README.txt"), "r") as f:
            content = f.read()
            self.assertEqual(content, "")
        self.assertEqual(len(list(repo.iter_commits())), 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
