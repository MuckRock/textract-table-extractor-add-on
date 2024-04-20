"""
Extract tables in documents on DocumentCloud using Amazon Textract
"""

import os
import sys
import zipfile
import requests
from PIL import Image
from textractor import Textractor
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures
from documentcloud.addon import AddOn
from documentcloud.exceptions import APIError


class TableExtractor(AddOn):
    """Extract tables using Amazon Textract"""

    def calculate_cost(self, documents):
        """Given a set of documents, counts the number of pages and returns a cost"""
        total_num_pages = 0
        for doc in documents:
            start_page = self.data.get("start_page", 1)
            end_page = self.data.get("end_page")
            last_page = 0
            if end_page <= doc.page_count:
                last_page = end_page
            else:
                last_page = doc.page_count
            pages_to_analyze = last_page - start_page + 1
            total_num_pages += pages_to_analyze
        cost = total_num_pages * 10
        return cost

    def validate(self):
        """Validate that we can run the analysis"""

        if self.get_document_count() is None:
            self.set_message(
                "It looks like no documents were selected. Search for some or "
                "select them and run again."
            )
            sys.exit(0)
        if not self.org_id:
            self.set_message("No organization to charge.")
            sys.exit(0)
        ai_credit_cost = self.calculate_cost(self.get_documents())
        try:
            self.charge_credits(ai_credit_cost)
        except ValueError:
            return False
        except APIError:
            return False
        return True

    def setup_credential_file(self):
        """Setup credential files for AWS CLI"""
        credentials = os.environ["TOKEN"]
        credentials_file_path = os.path.expanduser("~/.aws/credentials")
        # Create the ~/.aws directory if it doesn't exist
        aws_directory = os.path.dirname(credentials_file_path)
        if not os.path.exists(aws_directory):
            os.makedirs(aws_directory)
        with open(credentials_file_path, "w") as file:
            file.write(credentials)

    def download_image(self, url, filename):
        """Download an image from a URL and save it locally."""
        response = requests.get(url, timeout=20)
        with open(filename, "wb") as f:
            f.write(response.content)

    def convert_to_png(self, gif_filename, png_filename):
        """Convert a GIF image to PNG format."""
        gif_image = Image.open(gif_filename)
        gif_image.save(png_filename, "PNG")

    def main(self):
        """The main add-on functionality goes here."""
        output_format = self.data.get("output_format", "csv")
        start_page = self.data.get("start_page", 1)
        end_page = self.data.get("end_page", 1)
        if not self.validate():
            self.set_message(
                "You do not have sufficient AI credits to run this Add-On on this document set"
            )
            sys.exit(0)

        if end_page < start_page:
            self.set_message(
                "The end page you provided is smaller than the start page, try again"
            )
            sys.exit(0)
        if start_page < 1:
            self.set_message("Your start page is less than 1, please try again")
            sys.exit(0)

        self.setup_credential_file()
        extractor = Textractor(profile_name="default", region_name="us-east-1")
        os.makedirs("out")
        os.chdir("out")
        os.makedirs("tables")
        for document in self.get_documents():
            outer_bound = end_page + 1
            if end_page > document.page_count:
                outer_bound = document.page_count + 1
            for page_number in range(start_page, outer_bound):
                image_data = document.get_large_image(page_number)
                gif_filename = f"{document.id}-page{page_number}.gif"
                with open(gif_filename, 'wb') as f:
                    f.write(image_data)
                png_filename = f"{document.id}-page{page_number}.png"
                self.convert_to_png(gif_filename, png_filename)
                image = Image.open(png_filename)
                doc = extractor.analyze_document(
                    file_source=image,
                    features=[TextractFeatures.TABLES],
                    save_image=True,
                )
                if output_format == "csv":
                    os.chdir("tables")
                    for i in range(len(doc.tables)):
                        table = EntityList(doc.tables[i])
                        # print(table[0])
                        csv_filename = f"{document.id}-{page_number}-table{i}.csv"
                        csv_string = table[0].to_csv()
                        with open(csv_filename, "w") as csv_file:
                            csv_file.write(csv_string)
                    os.chdir("..")
                else:
                    os.chdir("tables")
                    for i in range(len(doc.tables)):
                        table = EntityList(doc.tables[i])
                        # print(table[0])
                        table[0].to_excel(
                            f"{document.id}-{page_number}-table{i}.xlsx"
                        )
                    os.chdir("..")

        with zipfile.ZipFile("all_tables.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk("tables"):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, "tables"))
        self.upload_file(open("all_tables.zip"))


if __name__ == "__main__":
    TableExtractor().main()
