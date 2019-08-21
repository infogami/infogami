# infogami
[![Build Status](https://travis-ci.org/internetarchive/infogami.svg?branch=master)](https://travis-ci.org/internetarchive/infogami)

The Open Library interface is powered by infogami -- a cleaner, simpler alternative to other wiki applications. But unlike other wikis, Infogami has the flexibility to handle different classes of data. Most wikis let you store unstructured pages -- big blocks of text. Infogami lets you store structured data.

In addition to this, infogami facilitates the creation of dynamic HTML templates and macros. This flexible environment enables users to create, share and build collaborative interfaces. With Open Library in particular, we are focused on building a productive and vital community focused on the discovery of books.

Applications are written by extending Infogami through two layers: plugins and templates. Plugins are Python modules that get loaded into Infogami through a special API. (See [an overview of Infogami plugins][6].) They are invoked by submitting HTTP requests to the application, either HTML form posts or direct GET requests. Plugins can use any library or application code that they wish, and they create Python objects to represent results, that then get expanded to HTML by templates. Templates are a mixture of HTML text and user-written code, in the spirit of PHP templates. The user-written code is in a special-purpose scripting language that is approximately a Python subset, which runs in a hopefully-secure server-side interpreter embedded in the Python app that has limited access to system functions and resources.

In this document, you'll learn how to develop for infogami, including building new templates for displaying your own data, running your own copy, and developing new features and plugins.

## Summary (Audience Statement)

This document describes the internal workings of the Open Library software, from a developers' point of view. You should read it if you are:

1) a software developer wanting to add new features to Open Library. To do this, you will also have to be a good Python programmer experienced in writing web server applications (not necessarily in Python). The document will explain the Open Library's software architecture and its internal interfaces, and will explain how to write extensions (plugins), but the sections about plugin writing will assume that you are familiar with Python and web programming in general.

If you do not yet know Python, you should first study the Python documentation or the free book Dive into Python. Python is an easy language to learn, but the OL codebase is probably not understandable by complete beginners.
For web server principles, the somewhat dated Philip and Alex's Guide to Web Publishing is still an informative read, though maybe someone can suggest something newer. You should also understand the principles of software security -- see David A Wheeler's page for many documents.

2) A user or web designer wanting to improve or customize the Open Library's user interface, either for yourself or for our whole community. You will mainly want to study the section about template programming. You will need to know how to write HTML and it will help if you've done some server-side template programming (such as in PHP). It will also help if you've had some exposure to Python, but the programming skills you'll need for template writing are generally less intense than they'd be for extension writing.

3) A general user just wanting to know how the software works behind the scenes. You might not understand all the details, but reading the doc should give you a general impression of how sites like this are put together.

4) A librarian or metadata maintainer wanting to process large volumes of metadata for import into the Open Library. If you only want to import a few books, it's probably easiest to use the web interface (or the Z39.50 interface once we have one). To import bulk data, you'll have to process it into a format that Open Library can understand, which may require programming, but you can use your own choices of languages and platforms for that purpose since you only have to create uploadable files, rather than use language-specific interfaces. You'll mainly want to look at the section about data formats and schemas.

If you just want to be an OL user accessing or editing book data, you do NOT need to read this doc. The doc is about how to customize and extend the software, not how to use it. As developers and designers, our goal is to make the site self-explanatory for users and not need much separate documentation, but we do have some user docs at /help.

## Introduction

Infogami is a wiki application framework built on web.py. Actual applications (like Open Library) are written by extending Infogami through two layers: plugins and templates. Plugins are Python modules that get loaded into Infogami through a special API. They are invoked by submitting HTTP requests to the application, either HTML form posts or direct GET requests. Plugins can use any library or application code that they wish, and they create Python objects to represent results, that then get expanded to HTML by templates. Templates are a mixture of HTML text and user-written code, approximately in the spirit of PHP templates. The user-written code is in a special-purpose scripting language that is approximately a Python subset, which runs in a hopefully-secure server-side interpreter (embedded in the Python app) that has limited access to system functions and resources.

## Continued

See docs @ https://openlibrary.org/dev/docs/infogami

